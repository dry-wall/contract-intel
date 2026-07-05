"""
The actual processing logic for one upload event. Called identically from
main.py's push endpoint (prod) and pull_worker.py's pull loop (local dev) —
neither entry point contains any business logic itself, they just deliver a
ProcessRequest to this one function. Phase 5 replaces the "extract only"
stub body here with the real LangGraph agent call; the idempotency guard and
GCS download stay exactly as they are.

Idempotency: Pub/Sub's at-least-once delivery means the same message can
arrive more than once (redelivery after a slow ack, network blip, etc).
We track completed job_ids in memory to skip duplicates. This is
intentionally simple for Phase 3 — it resets if the process restarts, which
is fine for now because there's no real work being done yet. Phase 11
upgrades this to a durable check (e.g. a Firestore/BigQuery marker) before
this matters in production, since by then a duplicate would mean redoing an
expensive LLM call rather than just re-extracting text.
"""
import logging

from app.gcs import download_pdf
from app.pdf_extract import extract_pages
from app.schemas.process import ProcessRequest

logger = logging.getLogger(__name__)

_processed_job_ids: set[int] = set()


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

    _processed_job_ids.add(payload.job_id)
    # Phase 5 replaces this return with the real LangGraph agent result.
    # Phase 6 replaces this log-only outcome with a Pub/Sub publish back to
    # Django's document-processed topic.
    return {"job_id": payload.job_id, "status": "extracted", "page_count": len(pages), "char_count": total_chars}
