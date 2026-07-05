"""
The router — this is the "agent decides the order of operations depending
on document type" feature from the architecture. Deliberately RULE-BASED
rather than another LLM call: the routing decision itself doesn't need
reasoning, it needs to be fast, free, and 100% predictable/testable. Saving
LLM calls for the two steps that actually need judgment (risk scoring,
explanation) is the same cost-discipline as the Flash-Lite/Pro split.

Policy (documented here because this table IS the interview talking point):
  NDA            -> skip risk scoring entirely; explain only clauses whose
                    type mentions confidentiality or term/duration.
                    Rationale: NDAs are short and low-complexity; full risk
                    scoring on every clause is overkill.
  MSA            -> full risk scoring on every clause; explain only HIGH-risk
                    ones. Rationale: MSAs are complex and risk-bearing enough
                    to warrant scoring everything, but a user only needs
                    plain-English help on the clauses that are actually risky.
  everything else (LEASE, EMPLOYMENT, OTHER) -> full risk scoring; explain
                    HIGH and MEDIUM risk clauses, a slightly more generous
                    default since these doc types are less standardized.
"""
from app.agent.state import AgentState

CONFIDENTIALITY_OR_TERM_KEYWORDS = ("confidential", "term", "duration", "non-disclosure")


def needs_risk_scoring(state: AgentState) -> str:
    """Conditional edge after extraction: NDA skips straight to target
    selection; everything else goes through risk scoring first."""
    if state["doc_type"] == "NDA":
        return "select_targets"
    return "risk_score"


def select_explain_targets(state: AgentState) -> AgentState:
    doc_type = state["doc_type"]

    if doc_type == "NDA":
        # No risk_scores exist for NDAs (skipped) — select by clause_type keyword instead.
        targets = [
            i
            for i, c in enumerate(state["clauses"])
            if any(kw in c["clause_type"].lower() for kw in CONFIDENTIALITY_OR_TERM_KEYWORDS)
        ]
    elif doc_type == "MSA":
        targets = [rs["clause_index"] for rs in state["risk_scores"] if rs["risk_category"] == "HIGH"]
    else:
        targets = [
            rs["clause_index"]
            for rs in state["risk_scores"]
            if rs["risk_category"] in ("HIGH", "MEDIUM")
        ]

    state["explain_targets"] = targets
    return state
