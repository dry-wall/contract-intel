"""
ProcessedEvent is the fixed contract published to the document-processed
topic. Its fields must exactly match what Django's consume_processed_events
management command expects. Changing a field name here means changing it on
both sides -- same discipline as Phase 3's ProcessRequest contract.
"""
from typing import Literal

from pydantic import BaseModel


class ProcessedEvent(BaseModel):
    job_id: int
    status: Literal["PROCESSING", "COMPLETE", "FAILED"]
    result: dict | None = None  # {"clauses": [...], "risk_scores": [...], "explanations": [...]}
    error_detail: str = ""
