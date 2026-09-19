"""COGNIFY execution-service — language runner abstraction.

``BaseRunner`` is the interface the evaluator programs against:
- ``language``: "python" | "java".
- ``compile(code, timeout)``: one-shot build step; returns compiler output on
  failure, else None. Interpreted languages return None (no build step — a
  Python SyntaxError therefore surfaces as RUNTIME_ERROR, not COMPILE_ERROR).
- ``run_single(code, stdin_data, timeout)``: execute once inside the sandbox.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .sandbox import RunResult, SandboxRunner


class BaseRunner(ABC):
    language: str = ""
    source_filename: str = ""

    def __init__(self, sandbox: SandboxRunner) -> None:
        self.sandbox = sandbox

    def compile(self, code: str, timeout_seconds: float) -> str | None:
        """Build step; None = no build step or build succeeded."""
        return None

    @abstractmethod
    def run_single(
        self, code: str, stdin_data: str, timeout_seconds: float
    ) -> RunResult:
        raise NotImplementedError


__all__ = ["BaseRunner"]
