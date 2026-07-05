"""
Structured-output schemas the LLM is constrained to return, via
with_structured_output(). This is what makes extraction/risk-scoring output
reliable JSON instead of free-text the rest of the pipeline has to parse.
"""
from pydantic import BaseModel, Field


class ExtractedClause(BaseModel):
    clause_type: str = Field(description="Short category name, e.g. 'Limitation of Liability'")
    text: str = Field(description="The exact clause text as it appears in the contract")
    page: int = Field(description="1-indexed page number this clause appears on")


class ClauseExtractionResult(BaseModel):
    clauses: list[ExtractedClause]


class RiskAssessment(BaseModel):
    risk_score: int = Field(ge=0, le=100, description="0=no risk, 100=extremely high risk")
    risk_category: str = Field(description="One of: LOW, MEDIUM, HIGH")
    rationale: str = Field(description="One or two sentences explaining the score")
