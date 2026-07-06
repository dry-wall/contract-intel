"""
Publishes to the document-processed topic -- the return half of the async
loop that started with Django's document-uploaded publish in Phase 2.
Mirrors documents/pubsub.py on the Django side: environment-agnostic,
since google-cloud-pubsub itself handles the emulator-vs-real switch via
the PUBSUB_EMULATOR_HOST env var.
"""
import json

from google.cloud import pubsub_v1

from app import config
from app.schemas.processed_event import ProcessedEvent

_publisher: pubsub_v1.PublisherClient | None = None


def get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def _publish(event: ProcessedEvent) -> str:
    topic_path = get_publisher().topic_path(config.GCP_PROJECT_ID, config.PUBSUB_PROCESSED_TOPIC)
    payload = event.model_dump()
    future = get_publisher().publish(topic_path, json.dumps(payload).encode("utf-8"))
    return future.result(timeout=30)


def publish_processing_started(job_id: int) -> str:
    """
    Early heartbeat, published as soon as handle_upload_event starts real
    work (after the scanned-PDF guard, before the agent runs). Lets Django
    flip the Job to PROCESSING immediately rather than sitting at PUBLISHED
    for however long the agent takes -- otherwise the status page looks stuck.
    """
    return _publish(ProcessedEvent(job_id=job_id, status="PROCESSING"))


def publish_processed_result(job_id: int, result: dict) -> str:
    """Published when the agent finishes successfully."""
    return _publish(ProcessedEvent(job_id=job_id, status="COMPLETE", result=result))


def publish_processing_failed(job_id: int, error_detail: str) -> str:
    """Published when anything in the pipeline raises after PROCESSING started."""
    return _publish(ProcessedEvent(job_id=job_id, status="FAILED", error_detail=error_detail))
