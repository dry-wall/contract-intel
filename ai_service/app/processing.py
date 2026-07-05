"""
The actual processing logic for one upload event. Called identically from
main.py's push endpoint (prod) and pull_worker.py's pull loop (local dev).

Phase 6 update: closes the async loop. Publishes a PROCESSING heartbeat as
soon as real work starts, a COMPLETE event with the full result on success,
or a FAILED event with an error_detail if anything raises. Django's
consume_processed_events command (Phase 6, Django side) is the other end of
this -- it's what actually flips the Job's status in Postgres.

Failure handling is deliberately broad (a single try/except around the
agent call) because ANY exception here -- a Vertex AI outage, a malformed
LLM response, a ChromaDB connection error -- must still result in a FAILED
event being published. An unhandled exception would leave the Job stuck at
PUBLISHED forever with no way for the ops dashboard to surface it, which is
worse than a possibly-noisy FAILED status.

Idempotency note: job_id is only added to _processed_job_ids on genuine
SUCCESS, never on failure. Marking a failed job as "processed" would defeat
Pub/Sub's redelivery for transient errors and would silently break Phase
1's admin "requeue_failed_jobs" recovery path (a requeue re-publishes the
same job_id expecting it to actually be retried). The real fix for
"a deterministic failure retries forever" is a Pub/Sub dead-letter topic
with a max-delivery-attempts cap -- tracked for Phase 11, not solved here.
"""
import logging

from app.agent.graph import run_agent
from app.gcs import download_pdf
from app.pdf_extract import extract_pages
from app.schemas.process import ProcessRequest
from app.sinks.pubsub_publish import (
    publish_processed_result,
    publish_processing_failed,
    publish_processing_started,
)

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

    try:
        pdf_bytes = download_pdf(payload.gcs_path)
        pages = extract_pages(pdf_bytes)
        total_chars = sum(len(p["text"]) for p in pages)

        logger.info(
            "job_id=%s extracted %d pages, %d total characters",
            payload.job_id, len(pages), total_chars,
        )

        if pages and (total_chars / len(pages)) < MIN_CHARS_PER_PAGE:
            logger.warning(
                "job_id=%s has only %.1f chars/page -- likely scanned/image PDF. "
                "Skipping agent call (OCR fallback not yet implemented; tracked in BACKLOG.md).",
                payload.job_id, total_chars / len(pages),
            )
            publish_processing_failed(
                payload.job_id,
                "Document appears to be a scanned/image PDF. OCR support is not yet available.",
            )
            # NOT added to _processed_job_ids: a scanned PDF is a genuine
            # dead end today, but if OCR support ships later and this event
            # gets redelivered/requeued, it should be retried, not silently
            # skipped as "already handled."
            return {"job_id": payload.job_id, "status": "needs_ocr"}

        # Heartbeat: tell Django we've started real work, before the
        # potentially-slow agent call. Keeps the status page from looking
        # stuck at PUBLISHED for the whole duration of the LLM calls.
        publish_processing_started(payload.job_id)

        agent_result = run_agent(pages, doc_type=payload.doc_type)

        logger.info(
            "job_id=%s agent finished: %d clauses, %d risk scores, %d explanations",
            payload.job_id,
            len(agent_result["clauses"]),
            len(agent_result["risk_scores"]),
            len(agent_result["explanations"]),
        )

        result = {
            "clauses": agent_result["clauses"],
            "risk_scores": agent_result["risk_scores"],
            "explanations": agent_result["explanations"],
        }
        publish_processed_result(payload.job_id, result)

        _processed_job_ids.add(payload.job_id)  # only mark done on genuine success
        return {"job_id": payload.job_id, "status": "processed", **result}

    except Exception as exc:
        # Broad on purpose: GCS errors, Vertex AI outages, ChromaDB
        # connection failures, malformed LLM output -- all of them must
        # result in a FAILED event, not a silently stuck job.
        #
        # Deliberately NOT added to _processed_job_ids here: doing so would
        # defeat Pub/Sub's redelivery for genuinely transient failures (a
        # momentary Vertex AI outage, say) and would also silently break
        # Phase 1's admin "requeue_failed_jobs" recovery path, since a
        # requeued job publishes the same job_id again and needs it to
        # actually be reprocessed, not skipped as a stale duplicate.
        # Real fix for "deterministic failures retry forever" is a Pub/Sub
        # dead-letter topic with a max-delivery-attempts cap -- tracked for
        # Phase 11 hardening, not solved here.
        logger.exception("job_id=%s processing failed", payload.job_id)
        publish_processing_failed(payload.job_id, str(exc))
        return {"job_id": payload.job_id, "status": "failed", "error_detail": str(exc)}
