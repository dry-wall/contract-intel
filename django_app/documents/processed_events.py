"""
Applies one document-processed event to the matching Job. Separated from
the Pub/Sub pull loop (consume_processed_events management command) so this
logic is testable without a live subscription -- mirrors the ai_service
pattern of keeping processing.py's business logic separate from
pull_worker.py's delivery mechanism.
"""
import logging

from .models import Job

logger = logging.getLogger(__name__)


def apply_processed_event(payload: dict) -> None:
    """
    payload shape (from ai_service's ProcessedEvent):
        {"job_id": int, "status": "PROCESSING"|"COMPLETE"|"FAILED",
         "result": dict|None, "error_detail": str}
    """
    job_id = payload["job_id"]
    status = payload["status"]

    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        # Don't crash the pull loop over a stale/malformed message -- log
        # loudly (this should never happen if Phase 2's publish is correct)
        # and move on so one bad message doesn't block the whole queue.
        logger.error("Received processed event for unknown job_id=%s, ignoring.", job_id)
        return

    if status == "PROCESSING":
        job.mark_processing()
    elif status == "COMPLETE":
        job.mark_complete(payload.get("result") or {})
    elif status == "FAILED":
        job.mark_failed(payload.get("error_detail", ""))
    else:
        logger.error("Unknown status '%s' in processed event for job_id=%s", status, job_id)
        return

    logger.info("job_id=%s -> %s", job_id, status)
