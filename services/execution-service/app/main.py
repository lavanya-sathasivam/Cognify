"""COGNIFY execution-service — safe code execution + test evaluation API.

Endpoints:
  GET  /health   — liveness check.
  POST /execute  — run student code (python/java) against test cases inside
                   an isolated Docker sandbox and return an ExecutionResult.

NOT implemented here: AI diagnosis, mastery, adaptive learning, frontend,
database access. This service is stateless.

``create_app`` accepts a ``runner_factory`` so unit tests can inject mocked
runners (no Docker needed). Production uses Docker-backed runners and fails
closed (503) when Docker is unavailable — student code is never executed on
the host.
"""
from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, HTTPException

from packages.problem_schema import normalize_language

from .evaluator import evaluate
from .java_runner import JavaRunner
from .models import ExecutionRequest, ExecutionResult
from .python_runner import PythonRunner
from .runners import BaseRunner
from .sandbox import SandboxUnavailableError

RunnerFactory = Callable[[str, float], BaseRunner]


def default_runner_factory(language: str, timeout_seconds: float) -> BaseRunner:
    norm = normalize_language(language)
    if norm == PythonRunner.language:
        return PythonRunner()
    if norm == JavaRunner.language:
        return JavaRunner()
    raise ValueError(f"Unsupported language {language!r}.")


def create_app(runner_factory: RunnerFactory | None = None) -> FastAPI:
    factory = runner_factory or default_runner_factory
    app = FastAPI(title="cognify-execution-service", version="0.2.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "execution-service"}

    @app.get("/languages")
    def languages() -> dict:
        return {"languages": [PythonRunner.language, JavaRunner.language]}

    @app.post("/execute", response_model=ExecutionResult)
    def execute(request: ExecutionRequest) -> ExecutionResult:
        try:
            runner = factory(request.language, request.timeout_seconds)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return evaluate(
                language=request.language,
                code=request.code,
                test_cases=request.to_test_cases(),
                runner=runner,
                timeout_seconds=request.timeout_seconds,
            )
        except SandboxUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()

__all__ = ["app", "create_app", "default_runner_factory"]
