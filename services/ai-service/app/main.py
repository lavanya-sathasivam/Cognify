"""COGNIFY ai-service — scaffold only.

No business logic yet (no AI diagnosis, hints, LLM calls).
Exposes GET /health for service liveness checks.
"""

from fastapi import FastAPI

app = FastAPI(title="cognify-ai-service", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-service"}
