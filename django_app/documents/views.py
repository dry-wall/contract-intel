"""
Phase 8: the real frontend, replacing every bare test form and JSON-only
endpoint built in earlier phases.

upload_document: unchanged ingestion logic (Phase 2), GET now renders the
    real upload.html page instead of the temporary test form.
documents_list: the dashboard — every document the user's org has uploaded.
job_status_page / job_status_json: the live status page and the JSON
    endpoint its JS polls every 2 seconds until COMPLETE or FAILED.
job_results_page: renders clauses/risk/explanations plus the Phase 7
    population-benchmark chart data, computed in-process (no extra HTTP
    round trip to the analytics app — this view calls its query functions
    directly, since they're already both server-side Python).
"""
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from analytics.queries import get_risk_category_distribution, get_risk_percentile

from .forms import DocumentUploadForm
from .models import Document, Job
from .pubsub import publish_document_uploaded
from .storage import upload_pdf

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def upload_document(request):
    if request.method == "GET":
        return render(
            request,
            "documents/upload.html",
            {"doc_types": Document.DocType.choices},
        )

    form = DocumentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    upload = form.cleaned_data["file"]
    doc_type = form.cleaned_data["doc_type"]

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


@login_required
def documents_list(request):
    jobs = (
        Job.objects.filter(document__organization=request.user.organization)
        .select_related("document")
        .order_by("-created_at")
    )
    return render(request, "documents/list.html", {"jobs": jobs})


def _get_own_job_or_404(request, job_id):
    """Scoped to the caller's own organization — a user cannot view another
    org's job by guessing an ID. 404, not 403, so existence isn't confirmed
    to someone who shouldn't see it (same pattern as Phase 7's benchmark view)."""
    return get_object_or_404(Job, pk=job_id, document__organization=request.user.organization)


@login_required
def job_status_page(request, job_id):
    job = _get_own_job_or_404(request, job_id)
    return render(request, "documents/status.html", {"job": job})


@login_required
def job_status_json(request, job_id):
    job = _get_own_job_or_404(request, job_id)
    return JsonResponse({"status": job.status, "error_detail": job.error_detail})


@login_required
def job_results_page(request, job_id):
    job = _get_own_job_or_404(request, job_id)
    if job.status != Job.Status.COMPLETE or not job.result:
        raise Http404("Results are not available for this job yet.")

    doc_type = job.document.doc_type
    raw_clauses = job.result.get("clauses", [])
    risk_scores = job.result.get("risk_scores", [])
    explanations = job.result.get("explanations", [])
    risk_by_index = {rs["clause_index"]: rs for rs in risk_scores}
    explanation_by_index = {e["clause_index"]: e["explanation"] for e in explanations}

    clauses = []
    has_scored_clauses = any(c["risk_category"] for c in clauses)
    for i, clause in enumerate(raw_clauses):
        risk = risk_by_index.get(i)
        entry = {
            "clause_type": clause["clause_type"],
            "text": clause["text"],
            "risk_category": risk["risk_category"] if risk else None,
            "risk_score": risk["risk_score"] if risk else None,
            "rationale": risk["rationale"] if risk else None,
            "explanation": explanation_by_index.get(i),
            "percentile": None,
            "population_size": 0,
        }
        if risk:
            benchmark = get_risk_percentile(
                doc_type=doc_type, clause_type=clause["clause_type"], risk_score=risk["risk_score"]
            )
            entry["percentile"] = benchmark["percentile"]
            entry["population_size"] = benchmark["population_size"]
        clauses.append(entry)

    org_distribution = get_risk_category_distribution(organization_id=request.user.organization_id)
    platform_distribution = get_risk_category_distribution(organization_id=None)

    return render(
        request,
        "documents/results.html",
        {
            "job": job,
            "clauses": clauses,
            "org_distribution": org_distribution,
            "platform_distribution": platform_distribution,
            "org_distribution_json": json.dumps(org_distribution),
            "platform_distribution_json": json.dumps(platform_distribution),
            "has_scored_clauses": has_scored_clauses,
        },
    )
