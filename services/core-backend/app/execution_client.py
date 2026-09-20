"""COGNIFY core-backend — execution-service HTTP client (production path).

Production architecture (Docker Compose):

    student.py
      -> HTTP POST EXECUTION_SERVICE_URL/execute
      -> execution-service
      -> PythonRunner
      -> DockerSandboxRunner
      -> isolated student container

This module is the ONLY production execution integration for student
submissions. It performs no execution itself, imports no Docker code,
and never instantiates a sandbox runner. Student code is only ever
sent over HTTP to execution-service; it is never executed locally.

The returned value is a plain ``dict`` in the existing
``ExecutionResult.to_dict()`` shape, so all downstream pipeline
helpers keep working unchanged:

    - pipe.execution_status_str()
    - pipe.to_student_view()
    - pipe.build_pack_for_submission()
    - pipe.attempt_from_execution()

Failure mapping (fail closed, never execute locally):

    - connection/timeout/5xx from execution-service
      -> ExecutionServiceUnavailable (student.py maps to HTTP 503)
    - non-200 (other) or malformed JSON/shape
      -> ExecutionServiceBadResponse (student.py maps to HTTP 502)
"""
from __future__ import annotations

import copy
import os
from typing import Any

import httpx

EXECUTION_SERVICE_URL_ENV: str = "EXECUTION_SERVICE_URL"
DEFAULT_BASE_URL: str = "http://execution-service:8002"
EXECUTE_PATH: str = "/execute"

VALID_STATUSES: frozenset[str] = frozenset(
    {"PASSED", "FAILED", "COMPILE_ERROR", "RUNTIME_ERROR", "TIMEOUT"}
)

_REQUIRED_TOP_KEYS: tuple[str, ...] = (
    "status",
    "language",
    "execution_time_ms",
    "stdout",
    "stderr",
    "tests",
    "passed_count",
    "failed_count",
    "failed_test_id",
    "expected_output",
    "actual_output",
)

_REQUIRED_TEST_KEYS: tuple[str, ...] = (
    "test_id",
    "passed",
    "input",
    "expected_output",
    "actual_output",
    "stdout",
    "stderr",
    "exit_code",
    "timed_out",
    "time_ms",
)


class ExecutionServiceError(Exception):
    """Base error for execution-service integration failures."""


class ExecutionServiceUnavailable(ExecutionServiceError):
    """execution-service unreachable or reports its sandbox unavailable."""


class ExecutionServiceBadResponse(ExecutionServiceError):
    """execution-service returned non-200 or a malformed execution result."""


def get_base_url(base_url: str | None = None) -> str:
    """Resolve the execution-service base URL (no trailing slash)."""
    raw = base_url if base_url is not None else os.getenv(
        EXECUTION_SERVICE_URL_ENV, DEFAULT_BASE_URL
    )
    if not isinstance(raw, str) or not raw.strip():
        return DEFAULT_BASE_URL
    return raw.strip().rstrip("/")


def build_payload(problem: Any, code: str, timeout_seconds: float) -> dict[str, Any]:
    """Build the POST /execute JSON payload for ``problem`` + ``code``."""
    if problem is None or not hasattr(problem, "all_tests"):
        raise TypeError("problem must provide all_tests().")
    language = getattr(problem, "language", None)
    if not isinstance(language, str) or not language.strip():
        raise ValueError("problem.language must be a non-empty string.")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string.")
    if isinstance(timeout_seconds, bool) or not isinstance(
        timeout_seconds, (int, float)
    ):
        raise ValueError("timeout_seconds must be a number.")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be positive.")
    tests: list[dict[str, str]] = []
    for case in problem.all_tests():
        test_id = getattr(case, "id", None)
        test_input = getattr(case, "input", None)
        expected = getattr(case, "expected_output", None)
        if not isinstance(test_id, str) or not isinstance(test_input, str):
            raise ValueError("problem tests must have str id/input.")
        if not isinstance(expected, str):
            raise ValueError("problem tests must have str expected_output.")
        tests.append(
            {"id": test_id, "input": test_input, "expected_output": expected}
        )
    if not tests:
        raise ValueError("problem must contain at least one test.")
    return {
        "language": language,
        "code": code,
        "tests": tests,
        "timeout_seconds": timeout,
    }


def _is_int(value: Any) -> bool:
    return type(value) is int


def validate_response(data: Any, problem: Any = None) -> dict[str, Any]:
    """Validate a POST /execute response body into the pipeline contract.

    Returns a deep copy of ``data``. Raises ExecutionServiceBadResponse
    on any missing key or type/consistency violation so callers fail
    closed (502) instead of crashing downstream (evidence/verification).
    """
    if not isinstance(data, dict):
        raise ExecutionServiceBadResponse(
            "Execution response must be a JSON object, "
            f"got {type(data).__name__}."
        )
    missing = [k for k in _REQUIRED_TOP_KEYS if k not in data]
    if missing:
        raise ExecutionServiceBadResponse(
            f"Execution response missing keys: {missing}."
        )
    status = data["status"]
    if not isinstance(status, str) or status.strip().upper() not in VALID_STATUSES:
        raise ExecutionServiceBadResponse(
            f"Execution response has invalid status {status!r}."
        )
    language = data["language"]
    if not isinstance(language, str) or not language.strip():
        raise ExecutionServiceBadResponse("Execution response language invalid.")
    if problem is not None:
        expected_lang = getattr(problem, "language", None)
        if isinstance(expected_lang, str) and expected_lang.strip():
            if language.strip().lower() != expected_lang.strip().lower():
                raise ExecutionServiceBadResponse(
                    f"Execution language {language!r} does not match "
                    f"problem language {expected_lang!r}."
                )
    exec_ms = data["execution_time_ms"]
    if not _is_int(exec_ms) or exec_ms < 0:
        raise ExecutionServiceBadResponse("execution_time_ms must be int >= 0.")
    stdout = data["stdout"]
    stderr = data["stderr"]
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise ExecutionServiceBadResponse("stdout/stderr must be str.")
    passed_count = data["passed_count"]
    failed_count = data["failed_count"]
    if not _is_int(passed_count) or passed_count < 0:
        raise ExecutionServiceBadResponse("passed_count must be int >= 0.")
    if not _is_int(failed_count) or failed_count < 0:
        raise ExecutionServiceBadResponse("failed_count must be int >= 0.")
    for key in ("failed_test_id", "expected_output", "actual_output"):
        value = data[key]
        if value is not None and not isinstance(value, str):
            raise ExecutionServiceBadResponse(f"{key} must be str or None.")
    tests = data["tests"]
    if not isinstance(tests, list):
        raise ExecutionServiceBadResponse("tests must be a list.")
    for entry in tests:
        if not isinstance(entry, dict):
            raise ExecutionServiceBadResponse("test entries must be objects.")
        missing_t = [k for k in _REQUIRED_TEST_KEYS if k not in entry]
        if missing_t:
            raise ExecutionServiceBadResponse(
                f"Test entry missing keys: {missing_t}."
            )
        if not isinstance(entry["test_id"], str) or not entry["test_id"]:
            raise ExecutionServiceBadResponse("test_id must be a non-empty str.")
        if not isinstance(entry["passed"], bool):
            raise ExecutionServiceBadResponse("test passed must be bool.")
        for key in (
            "input",
            "expected_output",
            "actual_output",
            "stdout",
            "stderr",
        ):
            if not isinstance(entry[key], str):
                raise ExecutionServiceBadResponse(f"test {key} must be str.")
        if not _is_int(entry["exit_code"]):
            raise ExecutionServiceBadResponse("test exit_code must be int.")
        if not isinstance(entry["timed_out"], bool):
            raise ExecutionServiceBadResponse("test timed_out must be bool.")
        if not _is_int(entry["time_ms"]) or entry["time_ms"] < 0:
            raise ExecutionServiceBadResponse("test time_ms must be int >= 0.")
    if passed_count + failed_count != len(tests):
        raise ExecutionServiceBadResponse(
            "passed_count + failed_count must equal len(tests)."
        )
    actual_failed = [t for t in tests if t["passed"] is False]
    actual_passed = [t for t in tests if t["passed"] is True]
    if len(actual_failed) != failed_count or len(actual_passed) != passed_count:
        raise ExecutionServiceBadResponse(
            "passed/failed counts disagree with per-test results."
        )
    if failed_count == 0:
        if (
            data["failed_test_id"] is not None
            or data["expected_output"] is not None
            or data["actual_output"] is not None
        ):
            raise ExecutionServiceBadResponse(
                "failed pointers must be None when failed_count is 0."
            )
        if any(t["passed"] is not True for t in tests):
            raise ExecutionServiceBadResponse(
                "all tests must pass when failed_count is 0."
            )
    else:
        decisive = actual_failed[0]
        if data["failed_test_id"] != decisive["test_id"]:
            raise ExecutionServiceBadResponse(
                "failed_test_id must match the first failing test."
            )
        if (
            data["expected_output"] != decisive["expected_output"]
            or data["actual_output"] != decisive["actual_output"]
        ):
            raise ExecutionServiceBadResponse(
                "expected/actual output must mirror the decisive failure."
            )
        if data["stdout"] != decisive["stdout"] or data["stderr"] != decisive["stderr"]:
            raise ExecutionServiceBadResponse(
                "stdout/stderr must mirror the decisive failure."
            )
    return copy.deepcopy(data)


def execute_problem(
    problem: Any,
    code: str,
    timeout_seconds: float = 5.0,
    *,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Execute ``code`` against ``problem`` via execution-service (HTTP).

    Single POST /execute with ALL tests. Returns a validated plain dict
    in the existing ExecutionResult.to_dict() shape (accepted by all
    pipeline helpers). Never executes code locally.
    """
    payload = build_payload(problem, code, timeout_seconds)
    url = get_base_url(base_url) + EXECUTE_PATH
    # Worst case the service runs each test up to timeout_seconds; give
    # the HTTP call generous headroom plus a floor for fast paths.
    http_timeout = max(
        10.0, float(payload["timeout_seconds"]) * (len(payload["tests"]) + 1) + 10.0
    )
    try:
        response = httpx.post(url, json=payload, timeout=http_timeout)
    except httpx.RequestError as exc:
        raise ExecutionServiceUnavailable(
            f"Execution service unreachable at {url}: {exc}."
        ) from exc
    if response.status_code in (502, 503, 504):
        raise ExecutionServiceUnavailable(
            f"Execution service unavailable (HTTP {response.status_code})."
        )
    if response.status_code != 200:
        detail = ""
        try:
            detail = response.text[:500]
        except Exception:  # pragma: no cover - defensive
            detail = ""
        raise ExecutionServiceBadResponse(
            f"Execution service returned HTTP {response.status_code}: {detail}."
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ExecutionServiceBadResponse(
            "Execution service returned non-JSON response."
        ) from exc
    return validate_response(data, problem=problem)


__all__ = [
    "DEFAULT_BASE_URL",
    "EXECUTE_PATH",
    "EXECUTION_SERVICE_URL_ENV",
    "VALID_STATUSES",
    "ExecutionServiceBadResponse",
    "ExecutionServiceError",
    "ExecutionServiceUnavailable",
    "build_payload",
    "execute_problem",
    "get_base_url",
    "validate_response",
]
