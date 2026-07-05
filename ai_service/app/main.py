"""FastAPI entrypoint. Real /process endpoint arrives in Phase 3."""
from fastapi import FastAPI

app = FastAPI(title="Contract Intelligence AI Service")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
