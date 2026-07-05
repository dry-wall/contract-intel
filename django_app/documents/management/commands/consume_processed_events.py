"""
LOCAL DEV ONLY. Blocking Pub/Sub pull loop consuming document-processed
events and applying them to the matching Job. Symmetric to ai_service's
pull_worker.py on the upload side. Phase 10 replaces this with a push
endpoint + view instead.

Run with: uv run python manage.py consume_processed_events

Gotcha handled: a long-running management command holds its DB connection
open far longer than a normal request-response cycle, which can go stale
(the classic "server has gone away" error). django.db.close_old_connections()
before each unit of work forces Django to check and transparently
reconnect if needed.
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from google.cloud import pubsub_v1

from documents.processed_events import apply_processed_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consumes document-processed events and updates Job status."

    def handle(self, *args, **options):
        import json

        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(
            settings.GCP_PROJECT_ID, settings.PUBSUB_PROCESSED_PULL_SUBSCRIPTION
        )

        def callback(message: pubsub_v1.subscriber.message.Message) -> None:
            close_old_connections()
            try:
                payload = json.loads(message.data)
                apply_processed_event(payload)
                message.ack()
            except Exception:
                logger.exception("Failed to apply processed event, nacking for redelivery")
                message.nack()

        self.stdout.write(f"Listening on {subscription_path} (Ctrl+C to stop)...")
        future = subscriber.subscribe(subscription_path, callback=callback)
        try:
            future.result()
        except KeyboardInterrupt:
            future.cancel()
            future.result()
