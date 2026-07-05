"""
The actual processing logic for one upload event. Called identically from
main.py's push endpoint (prod) and pull_worker.py's pull loop (local dev) —
neither entry point contains any business logic itself, they just deliver a
ProcessRequest to this one function.

Phase 5 update: replaces the Phase 3 "extract only" stub with the real
LangGraph agent call (app.agent.graph.run_agent). The idempotency guard and
GCS download are unchanged from Phase 3.

Scanned-PDF guard (partial fix for the backlog item raised after Phase 3's
manual test): if extracted text is near-zero relative to page count, this is
almost certainly a scanned/image PDF that pypdf can't read. Rather than
spend an LLM call reasoning over empty text, we short-circuit with a clear
"needs_ocr" status. This is DETECTION only — the actual OCR fallback
(rendering pages to images + pytesseract/Vision API) is still tracked as
future work; this guard just stops it from silently wasting money/producing
garbage until that's built.

Idempotency: Pub/Sub's at-least-once delivery means the same message can
arrive more than once (redelivery after a slow ack, network blip, etc).
We track completed job_ids in memory to skip duplicates. Phase 11 upgrades
this to a durable check (e.g. a Firestore/BigQuery marker) — now that real
LLM calls happen here, a duplicate is no longer just a wasted text-extract,
it's wasted Gemini spend, so that upgrade matters more than it did in Phase 3.
"""
import logging

from app.agent.graph import run_agent
from app.gcs import download_pdf
from app.pdf_extract import extract_pages
from app.schemas.process import ProcessRequest

logger = logging.getLogger(__name__)

_processed_job_ids: set[int] = set()

# Below this average chars-per-page, treat the PDF as likely scanned/image-based.
MIN_CHARS_PER_PAGE = 20


def handle_upload_event(payload: ProcessRequest) -> dict:
    if payload.job_id in _processed_job_ids:
        logger.info("Job %s already processed, skipping duplicate delivery.", payload.job_id)
        return {"job_id": payload.job_id, "status": "skipped_duplicate"}

    logger.info(
        "Processing job_id=%s document_id=%s doc_type=%s gcs_path=%s",
        payload.job_id, payload.document_id, payload.doc_type, payload.gcs_path,
    )

    pdf_bytes = download_pdf(payload.gcs_path)
    pages = extract_pages(pdf_bytes)
    total_chars = sum(len(p["text"]) for p in pages)

    logger.info(
        "job_id=%s extracted %d pages, %d total characters",
        payload.job_id, len(pages), total_chars,
    )

    if pages and (total_chars / len(pages)) < MIN_CHARS_PER_PAGE:
        logger.warning(
            "job_id=%s has only %.1f chars/page — likely scanned/image PDF. "
            "Skipping agent call (OCR fallback not yet implemented; tracked in BACKLOG.md).",
            payload.job_id, total_chars / len(pages),
        )
        _processed_job_ids.add(payload.job_id)
        return {
            "job_id": payload.job_id,
            "status": "needs_ocr",
            "page_count": len(pages),
            "char_count": total_chars,
        }

    agent_result = run_agent(pages, doc_type=payload.doc_type)

    logger.info(
        "job_id=%s agent finished: %d clauses, %d risk scores, %d explanations",
        payload.job_id,
        len(agent_result["clauses"]),
        len(agent_result["risk_scores"]),
        len(agent_result["explanations"]),
    )

    _processed_job_ids.add(payload.job_id)
    # Phase 6 replaces this log-only outcome with a Pub/Sub publish back to
    # Django's document-processed topic, carrying this same result payload.
    return {
        "job_id": payload.job_id,
        "status": "processed",
        "clauses": agent_result["clauses"],
        "risk_scores": agent_result["risk_scores"],
        "explanations": agent_result["explanations"],
    }
