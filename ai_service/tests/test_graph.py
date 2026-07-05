"""
Integration tests for the compiled graph. All LLM calls and RAG retrieval
are mocked (no real Vertex AI credentials or ChromaDB needed) — these tests
verify the GRAPH WIRING itself: that an NDA and an MSA genuinely take
different node paths, matching the router's documented policy.
"""
from unittest.mock import MagicMock, patch

from app.agent.graph import run_agent
from app.schemas.agent_io import ClauseExtractionResult, ExtractedClause, RiskAssessment


def _mock_extraction_result(clauses):
    return ClauseExtractionResult(
        clauses=[ExtractedClause(clause_type=c[0], text=c[1], page=1) for c in clauses]
    )


@patch("app.tools.explanation.get_explain_model")
@patch("app.tools.risk_scoring.retrieve_template")
@patch("app.tools.risk_scoring.get_risk_model")
@patch("app.tools.extraction.get_extract_model")
def test_nda_path_skips_risk_scoring_and_explains_confidentiality_only(
    mock_extract_model, mock_risk_model, mock_retrieve, mock_explain_model
):
    extraction_llm = MagicMock()
    extraction_llm.with_structured_output.return_value.invoke.return_value = _mock_extraction_result(
        [("Confidentiality", "Both parties shall keep information secret."), ("Governing Law", "Delaware law applies.")]
    )
    mock_extract_model.return_value = extraction_llm

    explain_llm = MagicMock()
    explain_llm.invoke.return_value = MagicMock(content="Plain-English explanation.")
    mock_explain_model.return_value = explain_llm

    pages = [{"page_number": 1, "text": "some NDA text"}]
    result = run_agent(pages, doc_type="NDA")

    # Risk scoring must NOT have run for an NDA.
    mock_risk_model.assert_not_called()
    mock_retrieve.assert_not_called()
    assert result["risk_scores"] == []

    # Only the Confidentiality clause (index 0) should have been explained.
    assert result["explain_targets"] == [0]
    assert len(result["explanations"]) == 1
    assert result["explanations"][0]["clause_index"] == 0
    assert result["done"] is True


@patch("app.tools.explanation.get_explain_model")
@patch("app.tools.risk_scoring.retrieve_template")
@patch("app.tools.risk_scoring.get_risk_model")
@patch("app.tools.extraction.get_extract_model")
def test_msa_path_runs_risk_scoring_and_explains_high_risk_only(
    mock_extract_model, mock_risk_model, mock_retrieve, mock_explain_model
):
    extraction_llm = MagicMock()
    extraction_llm.with_structured_output.return_value.invoke.return_value = _mock_extraction_result(
        [
            ("Limitation of Liability", "Liability is uncapped."),
            ("Payment Terms", "Net 30 days."),
        ]
    )
    mock_extract_model.return_value = extraction_llm

    mock_retrieve.return_value = [
        {"template_text": "template", "similarity": 0.8, "source": "Common Paper", "clause_type": "X", "standard_position": "market-standard"}
    ]

    risk_llm = MagicMock()
    # First clause scores HIGH, second scores LOW.
    risk_llm.with_structured_output.return_value.invoke.side_effect = [
        RiskAssessment(risk_score=90, risk_category="HIGH", rationale="Uncapped liability is unusual."),
        RiskAssessment(risk_score=10, risk_category="LOW", rationale="Standard payment terms."),
    ]
    mock_risk_model.return_value = risk_llm

    explain_llm = MagicMock()
    explain_llm.invoke.return_value = MagicMock(content="Plain-English explanation.")
    mock_explain_model.return_value = explain_llm

    pages = [{"page_number": 1, "text": "some MSA text"}]
    result = run_agent(pages, doc_type="MSA")

    # Risk scoring MUST have run for an MSA.
    assert mock_risk_model.called
    assert len(result["risk_scores"]) == 2
    assert result["risk_scores"][0]["risk_category"] == "HIGH"
    assert result["risk_scores"][1]["risk_category"] == "LOW"

    # Only the HIGH-risk clause (index 0) should have been explained.
    assert result["explain_targets"] == [0]
    assert len(result["explanations"]) == 1
    assert result["done"] is True


@patch("app.tools.risk_scoring.retrieve_template")
@patch("app.tools.risk_scoring.get_risk_model")
@patch("app.tools.extraction.get_extract_model")
def test_risk_scoring_falls_back_to_unfiltered_query_when_no_match(
    mock_extract_model, mock_risk_model, mock_retrieve
):
    """If retrieve_template(clause_type=X) finds nothing, the tool must retry
    without the clause_type filter rather than skip scoring entirely."""
    extraction_llm = MagicMock()
    extraction_llm.with_structured_output.return_value.invoke.return_value = _mock_extraction_result(
        [("Unusual Clause Type", "Some clause text.")]
    )
    mock_extract_model.return_value = extraction_llm

    # First call (with clause_type filter) returns nothing; second call
    # (unfiltered fallback) returns a match.
    mock_retrieve.side_effect = [
        [],
        [{"template_text": "t", "similarity": 0.5, "source": "s", "clause_type": "c", "standard_position": "p"}],
    ]

    risk_llm = MagicMock()
    risk_llm.with_structured_output.return_value.invoke.return_value = RiskAssessment(
        risk_score=50, risk_category="MEDIUM", rationale="..."
    )
    mock_risk_model.return_value = risk_llm

    with patch("app.tools.explanation.get_explain_model") as mock_explain_model:
        mock_explain_model.return_value.invoke.return_value = MagicMock(content="...")
        pages = [{"page_number": 1, "text": "text"}]
        result = run_agent(pages, doc_type="OTHER")

    assert mock_retrieve.call_count == 2
    assert result["risk_scores"][0]["template_match_source"] == "s"
