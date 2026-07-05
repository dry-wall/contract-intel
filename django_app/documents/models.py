"""
Core models for the product layer.

Document: metadata about an uploaded contract. Stores only the GCS path,
never the file bytes — the actual PDF lives in Cloud Storage (wired in
Phase 2).

Job: tracks one processing run of a Document through the async pipeline.
State transitions are centralized in methods (mark_published, mark_processing,
mark_complete, mark_failed) rather than scattered `job.status = X; job.save()`
calls elsewhere in the codebase. This is deliberate: every status change goes
through exactly one place, so it's auditable, and every method sets its own
consistent side effects (timestamps, error clearing, etc.) without relying on
whoever calls it to remember to do so.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Document(models.Model):
    class DocType(models.TextChoices):
        NDA = "NDA", "NDA"
        MSA = "MSA", "Master Service Agreement"
        LEASE = "LEASE", "Lease"
        EMPLOYMENT = "EMPLOYMENT", "Employment Agreement"
        OTHER = "OTHER", "Other"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents"
    )
    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.PROTECT, related_name="documents"
    )
    original_filename = models.CharField(max_length=512)
    doc_type = models.CharField(max_length=20, choices=DocType.choices, default=DocType.OTHER)
    # Path only — e.g. "raw/org7/ab12.pdf". The bytes live in GCS (Phase 2).
    gcs_path = models.CharField(max_length=1024)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["organization", "uploaded_at"])]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.doc_type})"


class Job(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PUBLISHED = "PUBLISHED", "Published"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETE = "COMPLETE", "Complete"
        FAILED = "FAILED", "Failed"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="jobs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    pubsub_message_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_detail = models.TextField(blank=True, default="")
    # Filled in by the Phase 6 callback once FastAPI finishes the agent run.
    result = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"Job #{self.pk} [{self.status}] for {self.document.original_filename}"

    # ---- state-transition methods ------------------------------------
    # Every status change in the whole codebase goes through one of these.

    def mark_published(self, message_id: str) -> None:
        """Called right after a successful Pub/Sub publish (Phase 2)."""
        self.status = self.Status.PUBLISHED
        self.pubsub_message_id = message_id
        self.save(update_fields=["status", "pubsub_message_id"])

    def mark_processing(self) -> None:
        """Called on the FastAPI 'started' heartbeat event (Phase 6)."""
        self.status = self.Status.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_complete(self, result: dict) -> None:
        """Called by the Phase 6 callback when the agent finishes successfully."""
        self.status = self.Status.COMPLETE
        self.result = result
        self.finished_at = timezone.now()
        self.error_detail = ""
        self.save(update_fields=["status", "result", "finished_at", "error_detail"])

    def mark_failed(self, error_detail: str) -> None:
        """Called by the Phase 6 callback (or a retry-exhaustion path) on failure."""
        self.status = self.Status.FAILED
        self.error_detail = error_detail
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "error_detail", "finished_at"])
