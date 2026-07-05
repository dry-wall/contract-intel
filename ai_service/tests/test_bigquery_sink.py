from unittest.mock import MagicMock, patch

from app.sinks.bigquery_sink import stream_clauses


def _clauses():
    return [
        {"clause_type": "Governing Law", "text": "Delaware law applies.", "page": 1},
        {"clause_type": "Limitation of Liability", "text": "Liability is uncapped.", "page": 1},
    ]


def _risk_scores():
    return [
        {
            "clause_index": 1,
            "risk_score": 90,
            "risk_category": "HIGH",
            "template_match_source": "Common Paper Mutual NDA",
            "template_similarity": 0.8,
        }
    ]


@patch("app.sinks.bigquery_sink._get_client")
def test_stream_clauses_builds_correct_rows_with_deterministic_ids(mock_get_client):
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []  # no errors
    mock_get_client.return_value = mock_client

    stream_clauses(
        job_id=42, document_id=7, organization_id=1, doc_type="MSA",
        clauses=_clauses(), risk_scores=_risk_scores(),
    )

    call_args = mock_client.insert_rows_json.call_args
    table_id, rows = call_args[0][0], call_args[0][1]
    row_ids = call_args[1]["row_ids"]

    assert table_id.endswith(".processed_clauses")
    assert len(rows) == 2
    assert row_ids == ["42-0", "42-1"]

    # Clause 0 (Governing Law) has no risk score entry -> NULL risk fields.
    assert rows[0]["clause_type"] == "Governing Law"
    assert rows[0]["risk_score"] is None
    assert rows[0]["risk_category"] is None

    # Clause 1 (Limitation of Liability) has a matching risk score.
    assert rows[1]["risk_score"] == 90
    assert rows[1]["risk_category"] == "HIGH"
    assert rows[1]["template_match_source"] == "Common Paper Mutual NDA"

    # Every row carries the job/document/org identifiers.
    for row in rows:
        assert row["job_id"] == 42
        assert row["document_id"] == 7
        assert row["organization_id"] == 1
        assert row["doc_type"] == "MSA"


@patch("app.sinks.bigquery_sink._get_client")
def test_stream_clauses_with_no_clauses_does_not_call_insert(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    stream_clauses(job_id=1, document_id=1, organization_id=1, doc_type="NDA", clauses=[], risk_scores=[])

    mock_client.insert_rows_json.assert_not_called()


@patch("app.sinks.bigquery_sink._get_client")
def test_stream_clauses_logs_insert_errors_without_raising(mock_get_client):
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = [{"index": 0, "errors": ["some BQ error"]}]
    mock_get_client.return_value = mock_client

    # Must not raise even though insert_rows_json reported errors.
    stream_clauses(job_id=1, document_id=1, organization_id=1, doc_type="MSA", clauses=_clauses(), risk_scores=[])


@patch("app.sinks.bigquery_sink._get_client")
def test_stream_clauses_swallows_client_exceptions(mock_get_client):
    mock_get_client.side_effect = RuntimeError("BigQuery temporarily unavailable")

    # Must not raise -- this is the "best effort, never fail the job" guarantee.
    stream_clauses(job_id=1, document_id=1, organization_id=1, doc_type="MSA", clauses=_clauses(), risk_scores=[])
