"""
Assembles the LangGraph agent. This is the one function processing.py calls
(replacing Phase 3's extract-only stub): run_agent(pages, doc_type) ->
ProcessResult-shaped dict. The graph itself has a guardrail: LangGraph's
recursion_limit caps total node executions so a routing bug can't loop
forever and silently rack up LLM costs.

Graph shape:
    extract --(NDA)--> select_targets --> explain --> END
    extract --(other)--> risk_score --> select_targets --> explain --> END
"""
from langgraph.graph import END, StateGraph

from app.agent.router import needs_risk_scoring, select_explain_targets
from app.agent.state import AgentState
from app.tools.explanation import explain_clauses
from app.tools.extraction import extract_clauses
from app.tools.risk_scoring import score_risks

# Cap on total node executions per run — prevents a routing bug or an
# unexpected cycle from looping indefinitely and burning LLM spend.
RECURSION_LIMIT = 10


def _explain_node(state: AgentState) -> AgentState:
    state = explain_clauses(state, state["explain_targets"])
    state["done"] = True
    return state


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("extract", extract_clauses)
    graph.add_node("risk_score", score_risks)
    graph.add_node("select_targets", select_explain_targets)
    graph.add_node("explain", _explain_node)

    graph.set_entry_point("extract")
    graph.add_conditional_edges(
        "extract", needs_risk_scoring, {"risk_score": "risk_score", "select_targets": "select_targets"}
    )
    graph.add_edge("risk_score", "select_targets")
    graph.add_edge("select_targets", "explain")
    graph.add_edge("explain", END)

    return graph.compile()


_compiled_graph = None


def run_agent(pages: list[dict], doc_type: str) -> dict:
    """
    pages: [{"page_number": int, "text": str}, ...] from Phase 3's PDF extraction.
    Returns the final AgentState as a plain dict — clauses, risk_scores
    (empty for NDAs, by design), and explanations.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()

    initial_state: AgentState = {
        "document_text": "\n\n".join(p["text"] for p in pages),
        "doc_type": doc_type,
        "pages": pages,
        "clauses": [],
        "risk_scores": [],
        "explanations": [],
        "explain_targets": [],
        "next_action": "",
        "done": False,
    }

    final_state = _compiled_graph.invoke(initial_state, config={"recursion_limit": RECURSION_LIMIT})
    return dict(final_state)
