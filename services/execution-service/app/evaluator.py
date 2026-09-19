"""COGNIFY execution-service — test evaluator.

Pipeline: student code -> language runner -> problem_schema.TestCase list
-> ExecutionResult.

Output comparison is deterministic: CRLF normalized, trailing whitespace
stripped per line, leading/trailing blank lines ignored. Raw ``stdout`` is
always preserved as ``actual_output``; only the comparison is normalized.

Top-level status precedence (first match wins):
  COMPILE_ERROR (build step failed) > TIMEOUT (any test timed out)
  > RUNTIME_ERROR (any non-zero exit) > FAILED (any output mismatch)
  > PASSED (all tests matched).

NOT implemented here: AI diagnosis, mastery, adaptive learning, frontend,
database access.
"""
from __future__ import annotations

from packages.problem_schema import TestCase, normalize_language

from .models import ExecutionResult, ExecutionStatus, TestCaseResult
from .runners import BaseRunner


def normalize_output(text: str) -> str:
    """Canonical form for output comparison."""
    if not isinstance(text, str):
        raise TypeError(f"output must be str, got {type(text).__name__}.")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    stripped = [line.rstrip() for line in lines]
    return "\n".join(stripped).strip()


def _compile_error_result(
    language: str, compiler_output: str, time_ms: int = 0
) -> ExecutionResult:
    return ExecutionResult(
        status=ExecutionStatus.COMPILE_ERROR,
        language=language,
        execution_time_ms=time_ms,
        stdout="",
        stderr=compiler_output,
        tests=[],
        passed_count=0,
        failed_count=0,
        failed_test_id=None,
        expected_output=None,
        actual_output=None,
    )


def evaluate(
    language: str,
    code: str,
    test_cases: list[TestCase] | tuple[TestCase, ...],
    runner: BaseRunner,
    timeout_seconds: float = 5.0,
) -> ExecutionResult:
    """Run ``code`` against ``test_cases`` via ``runner`` and grade the output."""
    norm_language = normalize_language(language)
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string.")
    cases = list(test_cases)
    if not cases:
        raise ValueError("test_cases must contain at least one TestCase.")
    for case in cases:
        if not isinstance(case, TestCase):
            raise TypeError(
                f"test_cases entries must be TestCase, got {type(case).__name__}."
            )
    if runner.language != norm_language:
        raise ValueError(
            f"Runner language {runner.language!r} does not support {norm_language!r}."
        )
    if isinstance(timeout_seconds, bool) or not isinstance(
        timeout_seconds, (int, float)
    ):
        raise ValueError("timeout_seconds must be a number.")
    if float(timeout_seconds) <= 0:
        raise ValueError("timeout_seconds must be positive.")

    compile_failure = runner.compile(code, float(timeout_seconds))
    if compile_failure is not None:
        return _compile_error_result(norm_language, compile_failure)

    results: list[TestCaseResult] = []
    for case in cases:
        run = runner.run_single(code, case.input, float(timeout_seconds))
        actual = run.stdout
        if run.timed_out:
            passed = False
        elif run.exit_code != 0:
            passed = False
        else:
            passed = normalize_output(actual) == normalize_output(case.expected_output)
        results.append(
            TestCaseResult(
                test_id=case.id,
                passed=passed,
                input=case.input,
                expected_output=case.expected_output,
                actual_output=actual,
                stdout=run.stdout,
                stderr=run.stderr,
                exit_code=run.exit_code,
                timed_out=run.timed_out,
                time_ms=run.time_ms,
            )
        )

    passed_count = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]
    total_ms = sum(r.time_ms for r in results)

    if not failed:
        status = ExecutionStatus.PASSED
    elif any(r.timed_out for r in failed):
        status = ExecutionStatus.TIMEOUT
    elif any(r.exit_code != 0 for r in failed):
        status = ExecutionStatus.RUNTIME_ERROR
    else:
        status = ExecutionStatus.FAILED

    decisive = failed[0] if failed else results[0]
    return ExecutionResult(
        status=status,
        language=norm_language,
        execution_time_ms=total_ms,
        stdout=decisive.stdout,
        stderr=decisive.stderr,
        tests=results,
        passed_count=passed_count,
        failed_count=len(failed),
        failed_test_id=decisive.test_id if failed else None,
        expected_output=decisive.expected_output if failed else None,
        actual_output=decisive.actual_output if failed else None,
    )


__all__ = ["evaluate", "normalize_output"]
