"""
Population-analytics queries against BigQuery's processed_clauses table
(Phase 7). This is the platform's OWN accumulated usage data streamed by
ai_service -- NOT the same "population" as Phase 4's CUAD corpus, which
lives in ChromaDB and only feeds the risk-scoring RAG comparison. Don't
conflate the two when reading this module.

Cost guardrail baked in, not left to caller discretion: every query here
requires a partition filter on extracted_at (via the `days` parameter) and
sets maximum_bytes_billed, since forgetting either on a clustered/partitioned
table is the single most common way to accidentally scan (and pay for) the
entire table.
"""
from django.conf import settings
from google.cloud import bigquery

DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_MAX_BYTES_BILLED = 100_000_000  # 100MB cap per query; dev-scale usage
                                          # is nowhere near this, so hitting the
                                          # cap means a query lost its partition
                                          # filter somehow -- fail loudly, don't
                                          # silently eat a large bill.

_client: bigquery.Client | None = None


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=settings.GCP_PROJECT_ID)
    return _client


def _table_id() -> str:
    return f"{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.processed_clauses"


def _run_query(sql: str, params: list) -> list[dict]:
    job_config = bigquery.QueryJobConfig(
        query_parameters=params,
        maximum_bytes_billed=DEFAULT_MAX_BYTES_BILLED,
    )
    query_job = _get_client().query(sql, job_config=job_config)
    return [dict(row) for row in query_job.result()]


def get_risk_percentile(
    doc_type: str, clause_type: str, risk_score: float, days: int = DEFAULT_LOOKBACK_DAYS
) -> dict:
    """
    Where does this clause's risk_score fall relative to every other clause
    of the same doc_type + clause_type the platform has ever scored? This is
    the "benchmark against the population" feature from the architecture --
    a document isn't just analyzed in isolation, it's compared against
    everything else that's come through.
    """
    sql = f"""
        SELECT
          COUNTIF(risk_score <= @risk_score) / COUNT(*) * 100 AS percentile,
          COUNT(*) AS population_size
        FROM `{_table_id()}`
        WHERE doc_type = @doc_type
          AND clause_type = @clause_type
          AND risk_score IS NOT NULL
          AND extracted_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
    """
    params = [
        bigquery.ScalarQueryParameter("risk_score", "FLOAT64", risk_score),
        bigquery.ScalarQueryParameter("doc_type", "STRING", doc_type),
        bigquery.ScalarQueryParameter("clause_type", "STRING", clause_type),
        bigquery.ScalarQueryParameter("days", "INT64", days),
    ]
    rows = _run_query(sql, params)
    if not rows or rows[0]["population_size"] == 0:
        return {"percentile": None, "population_size": 0}
    return rows[0]


def get_risk_category_distribution(
    organization_id: int | None = None, days: int = DEFAULT_LOOKBACK_DAYS
) -> list[dict]:
    """
    Counts of LOW/MEDIUM/HIGH across the population, optionally scoped to one
    organization (pass organization_id) vs the whole platform (pass None).
    Used to render "your org vs everyone" comparison charts.
    """
    org_filter = "AND organization_id = @organization_id" if organization_id is not None else ""
    sql = f"""
        SELECT risk_category, COUNT(*) AS count
        FROM `{_table_id()}`
        WHERE risk_category IS NOT NULL
          AND extracted_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
          {org_filter}
        GROUP BY risk_category
        ORDER BY risk_category
    """
    params = [bigquery.ScalarQueryParameter("days", "INT64", days)]
    if organization_id is not None:
        params.append(bigquery.ScalarQueryParameter("organization_id", "INT64", organization_id))
    return _run_query(sql, params)
