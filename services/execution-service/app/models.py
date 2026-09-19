"""COGNIFY execution-service — execution request/result models.

Scope: data shapes for the safe execution pipeline only.
  student code -> language-specific runner -> test cases -> execution result

Each execution result captures: status, language, execution time, stdout,
stderr, failed test information, expected output, and actual output.

NOT implemented here: AI diagnosis, mastery, adaptive learning, frontend,
database access. This service is stateless (no DB).

Test cases reuse ``packages.problem_schema.TestCase`` (single source of
truth); the API layer validates plain dicts via ``TestCaseInput`` and
converts them with ``TestCase.from_dict``.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from packages.problem_schema import TestCase, normalize_language

MAX_CODE_CHARS: int = 100_000
MAX_TESTS_PER_REQUEST: int = 50
MIN_TIMEOUT_SECONDS: float = 1.0
MAX_TIMEOUT_SECONDS: float = 30.0
DEFAULT_TIMEOUT_SECONDS: float = 5.0


class ExecutionStatus(str, Enum):
    """Terminal outcome of one execution request."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    COMPILE_ERROR = "COMPILE_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIMEOUT = "TIMEOUT"


class TestCaseInput(BaseModel):
    """API-level test case; converted to problem_schema.TestCase for evaluation."""

    id: str
    input: str = ""
    expected_output: str = ""

    def to_test_case(self) -> TestCase:
        return TestCase.from_dict(
            {"id": self.id, "input": self.input, "expected_output": self.expected_output}
        )


class ExecutionRequest(BaseModel):
    """Student code plus the test cases to evaluate it against."""

    language: str
    code: str
    tests: list[TestCaseInput] = Field(min_length=1, max_length=MAX_TESTS_PER_REQUEST)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, value: object) -> str:
        # Raises ValueError for anything but python/java (single source:
        # packages.problem_schema -> packages.taxonomy SUPPORTED_LANGUAGES).
        return normalize_language(value)  # type: ignore[arg-type]

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("code must be a non-empty string.")
        if len(value) > MAX_CODE_CHARS:
            raise ValueError(f"code exceeds {MAX_CODE_CHARS} characters.")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("timeout_seconds must be a number.")
        timeout = float(value)
        if not (MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS):
            raise ValueError(
                f"timeout_seconds must be in [{MIN_TIMEOUT_SECONDS}, "
                f"{MAX_TIMEOUT_SECONDS}], got {value!r}."
            )
        return timeout

    def to_test_cases(self) -> list[TestCase]:
        """Convert API inputs to problem_schema.TestCase models (validates IDs)."""
        return [t.to_test_case() for t in self.tests]


class TestCaseResult(BaseModel):
    """Per-test outcome: what was fed in, what came out, and whether it matched."""

    test_id: str
    passed: bool
    input: str
    expected_output: str
    actual_output: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    time_ms: int


class ExecutionResult(BaseModel):
    """Full execution outcome.

    Top-level ``stdout`` / ``stderr`` / ``failed_test_id`` /
    ``expected_output`` / ``actual_output`` mirror the *decisive* test
    (first non-passing test in run order, else the first test), so callers
    get the key failure without scanning ``tests``. For COMPILE_ERROR there
    are no per-test runs: ``stderr`` holds the compiler output.
    """

    status: ExecutionStatus
    language: str
    execution_time_ms: int
    stdout: str
    stderr: str
    tests: list[TestCaseResult]
    passed_count: int
    failed_count: int
    failed_test_id: str | None = None
    expected_output: str | None = None
    actual_output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_CODE_CHARS",
    "MAX_TESTS_PER_REQUEST",
    "MAX_TIMEOUT_SECONDS",
    "MIN_TIMEOUT_SECONDS",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "TestCaseInput",
    "TestCaseResult",
]
