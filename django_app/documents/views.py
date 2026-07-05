"""
The whole Ingestion layer lives in this one view:
  validate -> upload to GCS -> create Document -> create Job (PENDING)
  -> on successful DB commit, publish to Pub/Sub -> mark_published
  (or mark_failed if the publish itself fails).

The transaction.on_commit guard is deliberate: if anything after the GCS
upload raises and the DB transaction rolls back, we never publish an event
for a Document/Job that doesn't actually exist in Postgres. Publishing is
the LAST thing that happens, only once the commit is guaranteed to have
succeeded.
"""
import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .forms import DocumentUploadForm
from .models import Document, Job
from .pubsub import publish_document_uploaded
from .storage import upload_pdf

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def upload_document(request):
    if request.method == "GET":
        # Temporary unstyled test form — replaced by the real upload page in
        # Phase 8. Exists purely so this view is clickable without curl/CSRF
        # gymnastics while there's no real frontend yet.
        return render(request, "documents/upload_test_form.html", {"form": DocumentUploadForm()})

    form = DocumentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    upload = form.cleaned_data["file"]
    doc_type = form.cleaned_data["doc_type"]

    from django.conf import settings

    if upload.content_type != "application/pdf":
        return JsonResponse({"error": "Only PDF files are accepted."}, status=400)
    if upload.size > settings.MAX_UPLOAD_BYTES:
        limit_mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        return JsonResponse({"error": f"File exceeds the {limit_mb}MB limit."}, status=400)

    organization = request.user.organization
    if organization is None:
        return JsonResponse(
            {"error": "Your account has no organization assigned. Set one in /admin/ first."},
            status=400,
        )

    # Upload to GCS BEFORE opening the DB transaction — if this fails, we
    # never create a Document/Job for a file that doesn't exist in storage.
    gcs_path = upload_pdf(upload, organization.id)

    with transaction.atomic():
        document = Document.objects.create(
            owner=request.user,
            organization=organization,
            original_filename=upload.name,
            doc_type=doc_type,
            gcs_path=gcs_path,
        )
        job = Job.objects.create(document=document)  # defaults to PENDING

        def _publish_after_commit():
            try:
                message_id = publish_document_uploaded(job)
                job.mark_published(message_id)
            except Exception:
                logger.exception("Failed to publish document-uploaded for job %s", job.id)
                job.mark_failed("Failed to publish upload event to Pub/Sub.")

        transaction.on_commit(_publish_after_commit)

    return JsonResponse(
        {
            "document_id": document.id,
            "job_id": job.id,
            "status": job.status,  # reflects the outcome of the on_commit publish
        }
    )
