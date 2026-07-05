"""
Read-only benchmark view. Given a completed Job, shows each risk-scored
clause's percentile against the platform-wide population (Phase 7's
BigQuery data -- NOT the Phase 4 CUAD corpus), plus a risk-category
distribution comparing the user's own organization against everyone.

Deliberately simple/unstyled -- matching the Phase 2/3 pattern of a bare
functional view ahead of Phase 8's real frontend. The point of this view is
to prove the BigQuery query layer works end-to-end, not to be the final UI.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from documents.models import Job

from .queries import get_risk_category_distribution, get_risk_percentile


@login_required
def job_benchmark(request, job_id):
    job = get_object_or_404(Job, pk=job_id, document__organization=request.user.organization)

    if job.status != Job.Status.COMPLETE or not job.result:
        return JsonResponse({"error": "Job is not complete yet."}, status=400)

    doc_type = job.document.doc_type
    clauses = job.result.get("clauses", [])
    risk_scores = job.result.get("risk_scores", [])
    risk_by_index = {rs["clause_index"]: rs for rs in risk_scores}

    clause_benchmarks = []
    for i, clause in enumerate(clauses):
        risk = risk_by_index.get(i)
        if risk is None:
            continue  # e.g. NDA clauses that were never risk-scored
        benchmark = get_risk_percentile(
            doc_type=doc_type, clause_type=clause["clause_type"], risk_score=risk["risk_score"]
        )
        clause_benchmarks.append(
            {
                "clause_type": clause["clause_type"],
                "risk_score": risk["risk_score"],
                "risk_category": risk["risk_category"],
                "percentile": benchmark["percentile"],
                "population_size": benchmark["population_size"],
            }
        )

    org_distribution = get_risk_category_distribution(organization_id=request.user.organization_id)
    platform_distribution = get_risk_category_distribution(organization_id=None)

    return JsonResponse(
        {
            "job_id": job.id,
            "doc_type": doc_type,
            "clause_benchmarks": clause_benchmarks,
            "org_risk_distribution": org_distribution,
            "platform_risk_distribution": platform_distribution,
        }
    )
