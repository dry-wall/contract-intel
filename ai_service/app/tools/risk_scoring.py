"""
Tool 2 — risk scoring. For each extracted clause, retrieves the closest
market-standard template (Phase 4's retrieve_template) and asks Gemini Pro
— the one frontier-tier call in the whole pipeline — to score how much the
actual clause deviates from that baseline. This is where RAG lives: risk is
measured as deviation from a real corpus, not invented by the model alone.

Debug logging added around the Chroma and Gemini calls (Phase 10) to
pinpoint exactly which external call was hanging in production.
"""
import logging

from app.agent.llm import get_risk_model
from app.agent.state import AgentState
from app.rag.retrieval import retrieve_template
from app.schemas.agent_io import RiskAssessment

logger = logging.getLogger(__name__)

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


def score_risks(state: AgentState) -> AgentState:
    model = get_risk_model().with_structured_output(RiskAssessment)
    risk_scores = []
    for i, clause in enumerate(state["clauses"]):
        logger.info("risk_scoring: about to query Chroma for clause %d", i)
        matches = retrieve_template(clause["text"], clause_type=clause["clause_type"], n_results=1)
        if not matches:
            # Fall back to an unfiltered baseline match rather than giving up —
            # the clause_type the LLM assigned may not exactly match any
            # baseline clause_type string, but a broader match is still useful.
            matches = retrieve_template(clause["text"], n_results=1)
        logger.info("risk_scoring: Chroma query returned for clause %d (%d matches)", i, len(matches))

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

        logger.info("risk_scoring: about to call Gemini Pro for clause %d", i)
        assessment: RiskAssessment = model.invoke(prompt)
        logger.info("risk_scoring: Gemini Pro call returned for clause %d", i)

        risk_scores.append(
            {
                "clause_index": i,
                "risk_score": assessment.risk_score,
                "risk_category": assessment.risk_category,
                "template_match_source": template_source,
                "template_similarity": template_similarity,
                "rationale": assessment.rationale,
            }
        )
    state["risk_scores"] = risk_scores
    return state
