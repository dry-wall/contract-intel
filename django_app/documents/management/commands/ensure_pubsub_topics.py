"""
Creates the two Pub/Sub topics this project uses, if they don't already
exist. Works against the local emulator (when PUBSUB_EMULATOR_HOST is set)
and real Pub/Sub identically. Safe to run repeatedly.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1


class Command(BaseCommand):
    help = "Creates PUBSUB_UPLOAD_TOPIC and PUBSUB_PROCESSED_TOPIC if missing."

    def handle(self, *args, **options):
        publisher = pubsub_v1.PublisherClient()
        for topic_name in (settings.PUBSUB_UPLOAD_TOPIC, settings.PUBSUB_PROCESSED_TOPIC):
            topic_path = publisher.topic_path(settings.GCP_PROJECT_ID, topic_name)
            try:
                publisher.create_topic(name=topic_path)
                self.stdout.write(self.style.SUCCESS(f"Created topic '{topic_name}'."))
            except AlreadyExists:
                self.stdout.write(f"Topic '{topic_name}' already exists.")
