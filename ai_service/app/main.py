"""
FastAPI entrypoint. /process is a Pub/Sub PUSH endpoint — not used in local
dev (which uses pull_worker.py instead) but built and tested now so it's
ready when Phase 10 switches the production subscription to push.

Pub/Sub push delivery wraps the actual message in an envelope:
  {"message": {"data": "<base64>", "messageId": "...", ...}, "subscription": "..."}
We must decode message.data, parse it into ProcessRequest, and return 2xx
quickly — a non-2xx response tells Pub/Sub to redeliver. Heavy work runs in
a FastAPI BackgroundTask so the HTTP response isn't held up by processing.
"""
import base64
import json
import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import ValidationError

from app.processing import handle_upload_event
from app.schemas.process import ProcessRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Contract Intelligence AI Service")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/process")
async def process_push(request: Request, background_tasks: BackgroundTasks):
    envelope = await request.json()

    message = envelope.get("message")
    if message is None:
        # Malformed request, not a transient failure — don't ask Pub/Sub to
        # retry something that will never parse correctly.
        raise HTTPException(status_code=400, detail="Missing 'message' field in Pub/Sub envelope")

    try:
        raw = base64.b64decode(message["data"])
        payload = ProcessRequest.model_validate(json.loads(raw))
    except (KeyError, ValueError, ValidationError) as exc:
        logger.exception("Failed to parse Pub/Sub push envelope")
        raise HTTPException(status_code=400, detail=f"Bad message payload: {exc}") from exc

    # Return 200 immediately; do the real work after the response is sent so
    # Pub/Sub's push delivery isn't held open for the duration of processing.
    background_tasks.add_task(handle_upload_event, payload)
    return {"ack": True, "job_id": payload.job_id}
