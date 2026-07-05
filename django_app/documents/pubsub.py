"""
Pub/Sub publish helper. The publisher client itself is environment-agnostic:
the google-cloud-pubsub library checks the PUBSUB_EMULATOR_HOST environment
variable directly (not a Django setting) and transparently redirects to the
local emulator when it's set. In prod that variable is simply absent, so the
same code talks to real Pub/Sub with no branching needed here.
"""
import json

from django.conf import settings
from google.cloud import pubsub_v1

_publisher: pubsub_v1.PublisherClient | None = None


def get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_document_uploaded(job) -> str:
    """
    Publishes the upload event for a Job and returns the Pub/Sub message_id.
    Payload shape is the fixed contract FastAPI's /process endpoint expects
    (Phase 3) — changing these keys means changing both sides.
    """
    topic_path = get_publisher().topic_path(settings.GCP_PROJECT_ID, settings.PUBSUB_UPLOAD_TOPIC)
    payload = {
        "job_id": job.id,
        "document_id": job.document_id,
        "gcs_path": job.document.gcs_path,
        "doc_type": job.document.doc_type,
        "organization_id": job.document.organization_id,
    }
    future = get_publisher().publish(topic_path, json.dumps(payload).encode("utf-8"))
    return future.result(timeout=10)
