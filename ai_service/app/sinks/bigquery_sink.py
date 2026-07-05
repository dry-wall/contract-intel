"""
Streams one row per clause into BigQuery's processed_clauses table after a
document finishes processing successfully. This is what makes the platform
benchmark a document against every other document it has ever seen -- the
product insight from the architecture plan.

Deliberately best-effort: a BigQuery write failure must NOT fail the whole
job. The customer-facing outcome (Job.status=COMPLETE, result stored in
Postgres, Phase 6's loop) is already done by the time this runs -- analytics
streaming is a secondary concern layered on top, not part of the critical
path. If BigQuery is briefly unavailable, we log loudly and move on; we do
not want a flaky analytics pipeline to turn into a customer-facing failure.

Idempotency: clause_id is deterministic ("{job_id}-{index}") and passed as
BigQuery's insertId, which gives best-effort dedup on the same row within a
short window (~1 minute) if this ever gets called twice for the same job
(e.g. during the Phase 6 duplicate-processing scenario documented in
BACKLOG.md, before the flow_control fix). Not a permanent guarantee -- real
exactly-once semantics would need a durable idempotency key, which is
overkill for an analytics table where an occasional duplicate row skews
percentiles negligibly rather than corrupting anything.
"""
import logging
from datetime import datetime, timezone

from google.cloud import bigquery

from app import config

logger = logging.getLogger(__name__)

_client: bigquery.Client | None = None


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.GCP_PROJECT_ID)
    return _client


def stream_clauses(
    job_id: int,
    document_id: int,
    organization_id: int,
    doc_type: str,
    clauses: list[dict],
    risk_scores: list[dict],
) -> None:
    """
    clauses: [{"clause_type": str, "text": str, "page": int}, ...]
    risk_scores: [{"clause_index": int, "risk_score": int, "risk_category": str,
                    "template_match_source": str, "template_similarity": float}, ...]
                 (empty for doc types that skip risk scoring, e.g. NDA)
    """
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.processed_clauses"
    now = datetime.now(timezone.utc).isoformat()

    risk_by_index = {rs["clause_index"]: rs for rs in risk_scores}

    rows = []
    for i, clause in enumerate(clauses):
        risk = risk_by_index.get(i)
        rows.append(
            {
                "clause_id": f"{job_id}-{i}",
                "job_id": job_id,
                "document_id": document_id,
                "organization_id": organization_id,
                "doc_type": doc_type,
                "clause_type": clause["clause_type"],
                "clause_text": clause["text"],
                "risk_score": risk["risk_score"] if risk else None,
                "risk_category": risk["risk_category"] if risk else None,
                "template_match_source": risk["template_match_source"] if risk else None,
                "template_similarity": risk["template_similarity"] if risk else None,
                "extracted_at": now,
            }
        )

    if not rows:
        logger.info("job_id=%s has no clauses to stream to BigQuery.", job_id)
        return

    try:
        client = _get_client()
        row_ids = [row["clause_id"] for row in rows]
        errors = client.insert_rows_json(table_id, rows, row_ids=row_ids)
        if errors:
            logger.error("job_id=%s BigQuery streaming insert errors: %s", job_id, errors)
        else:
            logger.info("job_id=%s streamed %d clause rows to BigQuery.", job_id, len(rows))
    except Exception:
        # Best-effort: analytics streaming failing must never fail the job
        # itself. The customer-facing result is already safely in Postgres.
        logger.exception("job_id=%s failed to stream clauses to BigQuery (non-fatal)", job_id)
