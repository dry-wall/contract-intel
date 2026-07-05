"""
Creates the local-dev PULL subscription on the document-uploaded topic, if
it doesn't already exist. Run against the emulator during dev; in prod this
script is never run — Phase 10 creates a PUSH subscription instead, via a
gcloud command, not this script.

Run with:  uv run python -m scripts.ensure_pull_subscription
"""
import logging

from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import pubsub_v1

from app import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_UPLOAD_TOPIC)
    subscription_path = subscriber.subscription_path(
        config.GCP_PROJECT_ID, config.PUBSUB_UPLOAD_PULL_SUBSCRIPTION
    )

    # Fail fast with a clear message if the topic doesn't exist yet — this
    # almost always means Django's `ensure_pubsub_topics` hasn't been run.
    try:
        publisher.get_topic(topic=topic_path)
    except NotFound:
        raise SystemExit(
            f"Topic '{config.PUBSUB_UPLOAD_TOPIC}' does not exist yet. "
            "Run `ensure_pubsub_topics` on the Django side first."
        )

    try:
        subscriber.create_subscription(
    name=subscription_path, topic=topic_path, ack_deadline_seconds=600
)
        logger.info("Created pull subscription '%s'.", config.PUBSUB_UPLOAD_PULL_SUBSCRIPTION)
    except AlreadyExists:
        logger.info("Pull subscription '%s' already exists.", config.PUBSUB_UPLOAD_PULL_SUBSCRIPTION)


if __name__ == "__main__":
    main()
