"""COGNIFY ai-service — HTTP API (Step 7: AI diagnosis).

Endpoints:
  GET  /health    — liveness check.
  POST /diagnose  — diagnose one EvidencePack (LLM with fallback).

The LLM receives ONLY the EvidencePack from the request body. This
service holds no database connection, computes no mastery, generates no
hints, and makes no adaptive/roadmap decisions — it returns a grounded
diagnosis (concept_id, misconception_id, confidence, explanation,
evidence_refs) with ``source`` set to ``"llm"`` or ``"fallback"``.

``create_app`` accepts an injected LLM client so unit tests can use a
mocked LLM (no network, no API key). Production builds the client from
environment variables (``LLM_PROVIDER`` / ``LLM_API_KEY`` / ``LLM_MODEL``);
a missing key means fallback-only mode, never a crash.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException

from packages.evidence.models import EvidencePack

from .config import get_llm_config
from .llm_client import BaseLLMClient, OpenAICompatibleLLMClient
from .models import DiagnosisRequest, DiagnosisResult
from .service import diagnose_pack


def _default_client_from_env() -> BaseLLMClient | None:
    try:
        config = get_llm_config()
    except ValueError:
        return None
    if config.provider == "openai" and config.api_key:
        return OpenAICompatibleLLMClient(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
        )
    return None


def create_app(
    llm_client: BaseLLMClient | None = None,
    llm_client_factory: Callable[[], BaseLLMClient | None] | None = None,
) -> FastAPI:
    if llm_client_factory is not None:
        resolve: Callable[[], BaseLLMClient | None] = llm_client_factory
    elif llm_client is not None:
        _injected = llm_client

        def resolve() -> BaseLLMClient | None:
            return _injected
    else:
        _cached = _default_client_from_env()

        def _resolve() -> BaseLLMClient | None:
            return _cached

        resolve = _resolve

    app = FastAPI(title="cognify-ai-service", version="0.2.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "ai-service"}

    @app.post("/diagnose", response_model=DiagnosisResult)
    def diagnose(request: DiagnosisRequest) -> DiagnosisResult:
        try:
            pack = EvidencePack.from_dict(request.evidence_pack)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        client = resolve()
        return diagnose_pack(pack, client)

    return app


app = create_app()

__all__ = ["app", "create_app"]
