"""COGNIFY execution-service — Python runner (isolated, Docker-backed).

Student code is written to ``solution.py`` and run as
``python /workspace/solution.py`` with the test input on stdin, inside the
configured container image. Nothing executes on the host: see ``sandbox.py``.
"""
from __future__ import annotations

from .runners import BaseRunner
from .sandbox import RunResult, SandboxRunner

PYTHON_IMAGE: str = "python:3.11-slim"
SOLUTION_FILENAME: str = "solution.py"
RUN_COMMAND: list[str] = ["python", f"/workspace/{SOLUTION_FILENAME}"]


class PythonRunner(BaseRunner):
    """Execute Python submissions (no build step)."""

    language: str = "python"
    source_filename: str = SOLUTION_FILENAME

    def __init__(
        self, sandbox: SandboxRunner | None = None, image: str = PYTHON_IMAGE
    ) -> None:
        from .sandbox import DockerSandboxRunner

        super().__init__(sandbox or DockerSandboxRunner(image=image))

    def run_single(
        self, code: str, stdin_data: str, timeout_seconds: float
    ) -> RunResult:
        outcome = self.sandbox.run(
            files={SOLUTION_FILENAME: code},
            command=list(RUN_COMMAND),
            stdin_data=stdin_data,
            timeout_seconds=timeout_seconds,
        )
        return RunResult(
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            exit_code=outcome.exit_code,
            timed_out=outcome.timed_out,
            time_ms=outcome.time_ms,
        )


__all__ = ["PYTHON_IMAGE", "RUN_COMMAND", "SOLUTION_FILENAME", "PythonRunner"]
