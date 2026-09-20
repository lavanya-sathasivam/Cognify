"""COGNIFY core-backend — product API + learning-loop orchestration.

Endpoints:
  GET  /health              — liveness check.
  POST /student/sessions    — start a student session (canonical problem).
  GET  /student/problems/{} — safe problem metadata (no hidden answers).
   POST /student/submissions — submit code: execution -> evidence ->
                                diagnosis -> learner update -> intervention,
                                retry unlock, transfer, verification.
   GET  /student/journey      — journey stage, verification, recommendations.
   GET  /student/concepts     — read-only per-concept state + adaptive next
                                action (Step 20B).
   GET  /student/history      — read-only student-safe attempt history (20B).
   GET  /student/problems     — read-only safe problem catalog (Step 20B).

``create_app`` accepts an optional runner factory (Docker-backed by
default; scripted fakes in tests) so student code is never executed on
the host outside the existing sandbox abstraction. Browser access from
the web frontend is enabled via CORS (origins from
``STUDENT_CORS_ORIGINS``, default ``http://localhost:3000``).
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .student import RunnerFactory, StudentStore, create_student_router


def _cors_origins() -> list[str]:
    raw = os.getenv("STUDENT_CORS_ORIGINS", "http://localhost:3000")
    return [part.strip() for part in raw.split(",") if part.strip()]


def create_app(
    *,
    runner_factory: RunnerFactory | None = None,
    llm_client: Any = None,
    store: StudentStore | None = None,
) -> FastAPI:
    app = FastAPI(title="cognify-core-backend", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "core-backend"}

    app.include_router(
        create_student_router(
            store or StudentStore(),
            runner_factory=runner_factory,
            llm_client=llm_client,
        )
    )
    return app


app = create_app()

__all__ = ["app", "create_app"]
