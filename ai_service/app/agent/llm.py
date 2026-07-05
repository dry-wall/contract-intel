"""
Constructs the two Gemini model tiers used across the agent's tools.
This is the concrete implementation of the cost-routing decision: cheap
Flash-Lite for high-volume, low-reasoning steps (extraction, explanation),
expensive Pro only for the one step that actually needs deep reasoning
(risk scoring). Verify current model availability on the Vertex AI console
before relying on these — model generations retire on a schedule (Gemini
2.0 Flash-Lite was retired June 1, 2026; these are current as of this
build). Swapping either is a one-line env var change, not a code change.
"""
from langchain_google_vertexai import ChatVertexAI

from app import config


def get_extract_model() -> ChatVertexAI:
    """Flash-Lite: runs on every clause of every document. Cheap tier."""
    return ChatVertexAI(
        model_name=config.LLM_EXTRACT_MODEL,
        project=config.GCP_PROJECT_ID,
        location=config.VERTEX_LOCATION,
        temperature=0,  # deterministic structured extraction, not creative writing
    )


def get_risk_model() -> ChatVertexAI:
    """Pro: the one reasoning-heavy step, comparing a clause against its
    retrieved template. Only paid-frontier call in the whole pipeline."""
    return ChatVertexAI(
        model_name=config.LLM_RISK_MODEL,
        project=config.GCP_PROJECT_ID,
        location=config.VERTEX_LOCATION,
        temperature=0,
    )


def get_explain_model() -> ChatVertexAI:
    """Flash-Lite again — plain-English explanation is another high-volume,
    low-reasoning step."""
    return ChatVertexAI(
        model_name=config.LLM_EXTRACT_MODEL,
        project=config.GCP_PROJECT_ID,
        location=config.VERTEX_LOCATION,
        temperature=0.3,  # a little more natural phrasing is fine here
    )
