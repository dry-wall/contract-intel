"""
Tool 1 — clause extraction. Runs on Flash-Lite (cheap tier) since this
executes on every clause of every document. Uses with_structured_output()
to force clean ExtractedClause JSON instead of free text the rest of the
pipeline would have to parse unreliably.
"""
from app.agent.llm import get_extract_model
from app.agent.state import AgentState
from app.schemas.agent_io import ClauseExtractionResult

EXTRACTION_PROMPT = """You are a contract-review assistant. Read the following contract text \
and identify every distinct clause. For each clause, give a short category \
name (e.g. "Limitation of Liability", "Governing Law", "Termination", \
"Confidentiality", "Indemnification"), the exact clause text, and which \
page it appears on.

Document type: {doc_type}

Contract text (pages concatenated, page markers included):
{document_text}
"""


def extract_clauses(state: AgentState) -> AgentState:
    model = get_extract_model().with_structured_output(ClauseExtractionResult)

    page_marked_text = "\n\n".join(
        f"[PAGE {p['page_number']}]\n{p['text']}" for p in state["pages"]
    )
    prompt = EXTRACTION_PROMPT.format(doc_type=state["doc_type"], document_text=page_marked_text)

    result: ClauseExtractionResult = model.invoke(prompt)

    state["clauses"] = [
        {"clause_type": c.clause_type, "text": c.text, "page": c.page} for c in result.clauses
    ]
    return state
