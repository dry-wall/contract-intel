"""
Tool 2 — risk scoring. For each extracted clause, retrieves the closest
market-standard template (Phase 4's retrieve_template) and asks Gemini Pro
— the one frontier-tier call in the whole pipeline — to score how much the
actual clause deviates from that baseline. This is where RAG lives: risk is
measured as deviation from a real corpus, not invented by the model alone.

Phase 11: parallelized across clauses using a thread pool. Each clause's
Chroma query + Gemini Pro call is I/O-bound (network round-trips), so
threads genuinely help here — they release the GIL while waiting on the
network, unlike the sequential loop this replaces (tracked in BACKLOG.md
since Phase 6 as the "sequential risk-scoring doesn't scale" item).
Concurrency is bounded (MAX_WORKERS) rather than unbounded, so a
100-clause document doesn't fire 100 simultaneous Gemini requests and blow
through rate limits.
"""
import concurrent.futures
import logging

from app.agent.llm import get_risk_model
from app.agent.state import AgentState
from app.rag.retrieval import retrieve_template
from app.schemas.agent_io import RiskAssessment

logger = logging.getLogger(__name__)

MAX_WORKERS = 5

RISK_PROMPT = """You are a contract-risk analyst. Compare the ACTUAL CLAUSE below \
against the MARKET-STANDARD TEMPLATE it was matched to. Score how much the \
actual clause deviates from the template in ways that could disadvantage \
the party relying on this analysis (e.g. one-sided terms, missing \
protections, unusual obligations).
Clause type: {clause_type}
ACTUAL CLAUSE:
{clause_text}
MARKET-STANDARD TEMPLATE (source: {template_source}, similarity={similarity:.2f}):
{template_text}
Score 0-100 (0 = matches market standard closely, 100 = extremely one-sided \
or risky), classify as LOW (0-33) / MEDIUM (34-66) / HIGH (67-100), and give \
a one-to-two sentence rationale.
"""
NO_TEMPLATE_PROMPT = """You are a contract-risk analyst. No market-standard template was \
found for this clause type, so assess its risk based on general contract-drafting \
norms instead of a direct comparison.
Clause type: {clause_type}
ACTUAL CLAUSE:
{clause_text}
Score 0-100, classify as LOW (0-33) / MEDIUM (34-66) / HIGH (67-100), and give \
a one-to-two sentence rationale, noting that no baseline template was available.
"""


def _score_one_clause(index: int, clause: dict, model) -> dict:
    """Runs the Chroma lookup + Gemini Pro call for a single clause. Called
    concurrently, once per clause, by the thread pool below."""
    logger.info("risk_scoring: clause %d — querying Chroma", index)
    matches = retrieve_template(clause["text"], clause_type=clause["clause_type"], n_results=1)
    if not matches:
        # Fall back to an unfiltered baseline match rather than giving up —
        # the clause_type the LLM assigned may not exactly match any
        # baseline clause_type string, but a broader match is still useful.
        matches = retrieve_template(clause["text"], n_results=1)
    logger.info("risk_scoring: clause %d — Chroma returned %d matches", index, len(matches))

    if matches:
        template = matches[0]
        prompt = RISK_PROMPT.format(
            clause_type=clause["clause_type"],
            clause_text=clause["text"],
            template_source=template["source"],
            similarity=template["similarity"],
            template_text=template["template_text"],
        )
        template_source = template["source"]
        template_similarity = template["similarity"]
    else:
        prompt = NO_TEMPLATE_PROMPT.format(
            clause_type=clause["clause_type"], clause_text=clause["text"]
        )
        template_source = ""
        template_similarity = 0.0

    logger.info("risk_scoring: clause %d — calling Gemini Pro", index)
    assessment: RiskAssessment = model.invoke(prompt)
    logger.info("risk_scoring: clause %d — Gemini Pro returned", index)

    return {
        "clause_index": index,
        "risk_score": assessment.risk_score,
        "risk_category": assessment.risk_category,
        "template_match_source": template_source,
        "template_similarity": template_similarity,
        "rationale": assessment.rationale,
    }


def score_risks(state: AgentState) -> AgentState:
    model = get_risk_model().with_structured_output(RiskAssessment)
    clauses = state["clauses"]

    risk_scores: list[dict] = [None] * len(clauses)  # placeholder, filled by index below

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_index = {
            executor.submit(_score_one_clause, i, clause, model): i
            for i, clause in enumerate(clauses)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            # Let a single clause's failure surface as a real exception
            # rather than being silently swallowed — same "fail loudly"
            # principle used throughout this codebase (Phase 6 onward).
            risk_scores[index] = future.result()

    state["risk_scores"] = risk_scores
    return state
