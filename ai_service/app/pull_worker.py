"""
LOCAL DEV ONLY. A blocking Pub/Sub pull subscriber — actively fetches
messages from PUBSUB_UPLOAD_PULL_SUBSCRIPTION instead of waiting for a push.
This sidesteps having to expose your dev machine to the Pub/Sub emulator's
push mechanism (which gets awkward over WSL2/Docker Desktop networking).

Run with:  uv run python -m app.pull_worker

Calls the exact same app.processing.handle_upload_event() function that
main.py's /process push endpoint calls — so nothing about the actual
processing logic differs between dev (pull) and prod (push). Only the
delivery mechanism differs.

Phase 10 note: in production this file is not deployed at all — the
production subscription is a PUSH subscription pointed at the deployed
/process endpoint instead, per the plan's Phase 3 design.
"""
import logging

from google.cloud import pubsub_v1
from pydantic import ValidationError

from app import config
from app.processing import handle_upload_event
from app.schemas.process import ProcessRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _callback(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        payload = ProcessRequest.model_validate_json(message.data)
    except ValidationError:
        logger.exception("Bad message payload, nacking (will redeliver)")
        message.nack()
        return

    try:
        result = handle_upload_event(payload)
        logger.info("Processed: %s", result)
        message.ack()
    except Exception:
        logger.exception("Processing failed for job_id=%s, nacking for redelivery", payload.job_id)
        message.nack()


def main() -> None:
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(
        config.GCP_PROJECT_ID, config.PUBSUB_UPLOAD_PULL_SUBSCRIPTION
    )
    logger.info("Listening on %s (Ctrl+C to stop)...", subscription_path)

    future = subscriber.subscribe(subscription_path, callback=_callback)
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()
        future.result()


if __name__ == "__main__":
    main()
