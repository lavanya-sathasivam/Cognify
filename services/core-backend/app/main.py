"""COGNIFY core-backend — scaffold only.

No business logic yet (no diagnosis, mastery, adaptive, DB models).
Exposes GET /health for service liveness checks.
"""

from fastapi import FastAPI

app = FastAPI(title="cognify-core-backend", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "core-backend"}
