"""
The LangGraph agent's shared state. Every node (router, extract, risk_score,
explain) reads from and writes to this one structure — it's what flows
through the graph edges. Kept as a TypedDict (not a Pydantic model) because
that's what LangGraph's StateGraph expects natively.
"""
from typing import TypedDict


class Clause(TypedDict):
    clause_type: str
    text: str
    page: int


class RiskScore(TypedDict):
    clause_index: int  # index into state["clauses"]
    risk_score: int  # 0-100
    risk_category: str  # LOW / MEDIUM / HIGH
    template_match_source: str
    template_similarity: float
    rationale: str


class Explanation(TypedDict):
    clause_index: int
    explanation: str


class AgentState(TypedDict):
    document_text: str
    doc_type: str
    pages: list[dict]  # [{"page_number": int, "text": str}, ...] from Phase 3

    clauses: list[Clause]
    risk_scores: list[RiskScore]
    explanations: list[Explanation]
    explain_targets: list[int]  # clause indices the router selected for explanation

    next_action: str  # set by the router node; consumed by conditional edges
    done: bool
