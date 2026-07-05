"""
Pure unit tests for the router — no LLM, no mocking, no ChromaDB. These are
the cheapest, fastest tests in the whole suite and the most important ones
to keep green, since the router IS the "agent decides the order" feature.
"""
from app.agent.router import needs_risk_scoring, select_explain_targets


def _state(doc_type, clauses=None, risk_scores=None):
    return {
        "doc_type": doc_type,
        "clauses": clauses or [],
        "risk_scores": risk_scores or [],
        "explain_targets": [],
    }


def test_nda_skips_risk_scoring():
    assert needs_risk_scoring(_state("NDA")) == "select_targets"


def test_msa_requires_risk_scoring():
    assert needs_risk_scoring(_state("MSA")) == "risk_score"


def test_other_doc_types_require_risk_scoring():
    for dt in ("LEASE", "EMPLOYMENT", "OTHER"):
        assert needs_risk_scoring(_state(dt)) == "risk_score"


def test_nda_selects_confidentiality_and_term_clauses_by_keyword():
    clauses = [
        {"clause_type": "Confidentiality", "text": "..."},
        {"clause_type": "Governing Law", "text": "..."},
        {"clause_type": "Term and Termination", "text": "..."},
        {"clause_type": "Notices", "text": "..."},
    ]
    state = select_explain_targets(_state("NDA", clauses=clauses))
    assert state["explain_targets"] == [0, 2]  # Confidentiality, Term and Termination


def test_msa_selects_only_high_risk_clauses():
    clauses = [{"clause_type": "X", "text": "..."}] * 3
    risk_scores = [
        {"clause_index": 0, "risk_category": "LOW"},
        {"clause_index": 1, "risk_category": "HIGH"},
        {"clause_index": 2, "risk_category": "MEDIUM"},
    ]
    state = select_explain_targets(_state("MSA", clauses=clauses, risk_scores=risk_scores))
    assert state["explain_targets"] == [1]


def test_other_doc_types_select_high_and_medium():
    clauses = [{"clause_type": "X", "text": "..."}] * 3
    risk_scores = [
        {"clause_index": 0, "risk_category": "LOW"},
        {"clause_index": 1, "risk_category": "HIGH"},
        {"clause_index": 2, "risk_category": "MEDIUM"},
    ]
    state = select_explain_targets(_state("LEASE", clauses=clauses, risk_scores=risk_scores))
    assert state["explain_targets"] == [1, 2]
