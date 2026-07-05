"""
Creates the pull subscription Django uses to consume document-processed
events, if it doesn't already exist. Mirrors ai_service's
ensure_pull_subscription.py script on the other side of the loop. Local
dev only -- Phase 10 creates a PUSH subscription instead, via gcloud.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import pubsub_v1


class Command(BaseCommand):
    help = "Creates the pull subscription on PUBSUB_PROCESSED_TOPIC if missing."

    def handle(self, *args, **options):
        publisher = pubsub_v1.PublisherClient()
        subscriber = pubsub_v1.SubscriberClient()

        topic_path = publisher.topic_path(settings.GCP_PROJECT_ID, settings.PUBSUB_PROCESSED_TOPIC)
        subscription_path = subscriber.subscription_path(
            settings.GCP_PROJECT_ID, settings.PUBSUB_PROCESSED_PULL_SUBSCRIPTION
        )

        try:
            publisher.get_topic(topic=topic_path)
        except NotFound:
            self.stderr.write(
                f"Topic '{settings.PUBSUB_PROCESSED_TOPIC}' does not exist yet. "
                "Run `ensure_pubsub_topics` first."
            )
            return

        try:
            subscriber.create_subscription(name=subscription_path, topic=topic_path)
            self.stdout.write(
                self.style.SUCCESS(f"Created subscription '{settings.PUBSUB_PROCESSED_PULL_SUBSCRIPTION}'.")
            )
        except AlreadyExists:
            self.stdout.write(f"Subscription '{settings.PUBSUB_PROCESSED_PULL_SUBSCRIPTION}' already exists.")
