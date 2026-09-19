"""COGNIFY execution-service — scaffold only.

No business logic yet (no code execution, sandbox, test evaluation).
Exposes GET /health for service liveness checks.
"""

from fastapi import FastAPI

app = FastAPI(title="cognify-execution-service", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "execution-service"}
