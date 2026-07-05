"""
Tool 3 — plain-English explanation. Runs on Flash-Lite. Only explains
clauses the router decided are worth explaining (see agent/router.py) —
e.g. HIGH-risk clauses for an MSA, or all clauses for a short NDA.
"""
from app.agent.llm import get_explain_model
from app.agent.state import AgentState

EXPLAIN_PROMPT = """Explain the following contract clause in one short paragraph, \
in plain English a non-lawyer can understand. Focus on what it means \
practically and why it matters.

Clause type: {clause_type}
Clause text: {clause_text}
"""


def explain_clauses(state: AgentState, clause_indices: list[int]) -> AgentState:
    model = get_explain_model()
    explanations = list(state.get("explanations", []))

    for i in clause_indices:
        clause = state["clauses"][i]
        prompt = EXPLAIN_PROMPT.format(clause_type=clause["clause_type"], clause_text=clause["text"])
        response = model.invoke(prompt)
        explanations.append({"clause_index": i, "explanation": response.content})

    state["explanations"] = explanations
    return state
