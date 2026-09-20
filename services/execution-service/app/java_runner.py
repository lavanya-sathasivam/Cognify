"""COGNIFY execution-service — Java runner (isolated, Docker-backed).

Convention: the submission must define ``public class Main`` (file
``Main.java``). Pipeline per request:
  1. compile once: ``javac /workspace/Main.java`` -> failure = COMPILE_ERROR
  2. run per test: ``java -cp /workspace Main`` with the test input on stdin

Nothing executes on the host: see ``sandbox.py``.
"""
from __future__ import annotations

from .runners import BaseRunner
from .sandbox import RunResult, SandboxRunner

JAVA_IMAGE: str = "eclipse-temurin:17-jdk"
SOURCE_FILENAME: str = "Main.java"
CLASS_NAME: str = "Main"
COMPILE_COMMAND: list[str] = ["javac", f"/workspace/{SOURCE_FILENAME}"]
RUN_COMMAND: list[str] = [
    "sh",
    "-c",
    "javac /workspace/Main.java && java -cp /workspace Main",
]

class JavaRunner(BaseRunner):
    """Compile-then-run Java submissions."""

    language: str = "java"
    source_filename: str = SOURCE_FILENAME

    def __init__(
        self, sandbox: SandboxRunner | None = None, image: str = JAVA_IMAGE
    ) -> None:
        from .sandbox import DockerSandboxRunner

        super().__init__(
            sandbox or DockerSandboxRunner(image=image)
        )

    def compile(self, code: str, timeout_seconds: float) -> str | None:
        outcome = self.sandbox.run(
            files={SOURCE_FILENAME: code},
            command=list(COMPILE_COMMAND),
            stdin_data="",
            timeout_seconds=timeout_seconds,
        )
        if outcome.timed_out:
            return f"TIMEOUT: compilation exceeded {timeout_seconds}s wall-clock limit."
        if outcome.exit_code != 0:
            return outcome.stderr or outcome.stdout or "javac failed."
        return None

    def run_single(
        self, code: str, stdin_data: str, timeout_seconds: float
    ) -> RunResult:
        outcome = self.sandbox.run(
            files={SOURCE_FILENAME: code},
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


__all__ = [
    "CLASS_NAME",
    "COMPILE_COMMAND",
    "JAVA_IMAGE",
    "RUN_COMMAND",
    "SOURCE_FILENAME",
    "JavaRunner",
]