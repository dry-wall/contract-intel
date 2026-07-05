from django.contrib import admin

from .models import Document, Job


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "doc_type", "owner", "organization", "uploaded_at")
    list_filter = ("doc_type", "organization")
    search_fields = ("original_filename", "owner__username")
    readonly_fields = ("gcs_path", "uploaded_at")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    # This list view IS the ops dashboard: staff can see every job's status,
    # filter to just FAILED ones, and search by document filename — without
    # any custom dashboard code.
    list_display = (
        "id",
        "document",
        "status",
        "created_at",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "document__doc_type")
    search_fields = ("document__original_filename", "pubsub_message_id")
    readonly_fields = (
        "created_at",
        "started_at",
        "finished_at",
        "pubsub_message_id",
        "result",
    )
    actions = ["requeue_failed_jobs"]

    @admin.action(description="Reset selected FAILED jobs back to PENDING for re-publish")
    def requeue_failed_jobs(self, request, queryset):
        # Deliberately only touches FAILED jobs — re-queuing a job that's
        # currently PROCESSING would race with the real pipeline. The actual
        # re-publish (Pub/Sub call) is wired in Phase 2/6; this action just
        # resets state so that later logic can pick it up.
        updated = queryset.filter(status=Job.Status.FAILED).update(
            status=Job.Status.PENDING, error_detail=""
        )
        self.message_user(request, f"{updated} job(s) reset to PENDING.")
