"""COGNIFY execution-service — isolated sandbox abstraction.

SECURITY CONTRACT (enforced by construction + unit tests):
- Student code NEVER runs on the host. The only subprocess invocation in this
  service targets the ``docker`` CLI; interpreters/compilers run exclusively
  inside containers.
- No ``shell=True``, no ``eval``/``exec``/``compile`` of student code, no
  ``os.system`` anywhere in this service.
- Containers run with ``--network none`` (no network access).
- Every run has a wall-clock timeout (``subprocess`` timeout on the docker
  CLI plus a best-effort ``docker kill`` of the named container).
- Resource limits are always applied: ``--memory`` / ``--memory-swap`` /
  ``--cpus`` / ``--pids-limit``.
- No environment variables or secrets are forwarded into the container: the
  command never contains ``-e`` / ``--env`` / ``--env-file``.

If Docker is unavailable, runs fail CLOSED with ``SandboxUnavailableError``
(503 at the API). There is deliberately NO host fallback — executing
untrusted code on the host is worse than refusing the request.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MEMORY: str = "256m"
DEFAULT_CPUS: str = "1.0"
DEFAULT_PIDS_LIMIT: int = 128
CONTAINER_WORKDIR: str = "/workspace"


class SandboxUnavailableError(RuntimeError):
    """Raised when no isolated backend (Docker) is available. Fail closed."""


@dataclass(frozen=True)
class SandboxResult:
    """Raw outcome of one isolated container invocation."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    time_ms: int


@dataclass(frozen=True)
class RunResult:
    """Runner-layer outcome for a single test (or compile) step."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    time_ms: int
    compile_error: str | None = None


class SandboxRunner(ABC):
    """Abstraction over an isolated backend (Docker today, mocks in tests)."""

    @abstractmethod
    def run(
        self,
        files: dict[str, str],
        command: list[str],
        stdin_data: str,
        timeout_seconds: float,
    ) -> SandboxResult:
        """Run ``command`` in isolation with ``files`` mounted at /workspace."""
        raise NotImplementedError


def docker_available(docker_bin: str = "docker") -> bool:
    """True iff the docker CLI exists AND the daemon responds."""
    if shutil.which(docker_bin) is None:
        return False
    try:
        proc = subprocess.run(
            [docker_bin, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class DockerSandboxRunner(SandboxRunner):
    """Runs commands inside throwaway Docker containers.

    Each invocation: fresh temp dir -> write files -> ``docker run --rm``
    with isolation flags -> capture output -> remove temp dir. The temp dir
    is mounted read-write (the JDK/Python toolchains need a writable cwd for
    e.g. ``Main.class``); isolation comes from the container boundary, not
    the mount flags.
    """

    def __init__(
        self,
        image: str,
        memory: str = DEFAULT_MEMORY,
        cpus: str = DEFAULT_CPUS,
        pids_limit: int = DEFAULT_PIDS_LIMIT,
        network: str = "none",
        docker_bin: str = "docker",
        workdir_base: str | None = None,
    ) -> None:
        if not isinstance(image, str) or not image.strip():
            raise ValueError("image must be a non-empty string.")
        self.image = image.strip()
        self.memory = memory
        self.cpus = cpus
        self.pids_limit = pids_limit
        self.network = network
        self.docker_bin = docker_bin
        self.workdir_base = workdir_base

    def build_command(self, host_dir: str, container_name: str) -> list[str]:
        """Full ``docker run`` argv (no env forwarding flags, ever)."""
        return [
            self.docker_bin,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            self.network,
            "--memory",
            self.memory,
            "--memory-swap",
            self.memory,
            "--cpus",
            self.cpus,
            "--pids-limit",
            str(self.pids_limit),
            "-v",
            f"{host_dir}:{CONTAINER_WORKDIR}",
            "-w",
            CONTAINER_WORKDIR,
            "-i",
            self.image,
        ]

    def run(
        self,
        files: dict[str, str],
        command: list[str],
        stdin_data: str,
        timeout_seconds: float,
    ) -> SandboxResult:
        if not docker_available(self.docker_bin):
            raise SandboxUnavailableError(
                "Docker is unavailable; refusing to execute student code on the host."
            )
        if not command:
            raise ValueError("command must be a non-empty argv list.")
        host_dir = tempfile.mkdtemp(prefix="cognify-exec-", dir=self.workdir_base)
        try:
            for name, content in files.items():
                target = Path(host_dir) / name
                if ".." in Path(name).parts or Path(name).is_absolute():
                    raise ValueError(f"Unsafe file name {name!r}.")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            container_name = f"cognify-exec-{uuid.uuid4().hex[:12]}"
            argv = self.build_command(host_dir, container_name) + list(command)
            start = time.monotonic()
            try:
                proc = subprocess.run(
                    argv,
                    input=stdin_data.encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_seconds,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return SandboxResult(
                    stdout=proc.stdout.decode("utf-8", errors="replace"),
                    stderr=proc.stderr.decode("utf-8", errors="replace"),
                    exit_code=proc.returncode,
                    timed_out=False,
                    time_ms=elapsed_ms,
                )
            except subprocess.TimeoutExpired as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                self._kill_container(container_name)
                partial = b"".join(
                    chunk for chunk in (exc.stdout, exc.stderr) if chunk
                )
                return SandboxResult(
                    stdout="",
                    stderr=(
                        (partial.decode("utf-8", errors="replace") + "\n"
                         if partial else "")
                        + f"TIMEOUT: exceeded {timeout_seconds}s wall-clock limit."
                    ),
                    exit_code=-1,
                    timed_out=True,
                    time_ms=elapsed_ms,
                )
        finally:
            shutil.rmtree(host_dir, ignore_errors=True)

    def _kill_container(self, container_name: str) -> None:
        """Best-effort cleanup so timed-out containers do not linger."""
        try:
            subprocess.run(
                [self.docker_bin, "kill", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass


@dataclass
class FakeSandboxRunner(SandboxRunner):
    """Scripted in-memory sandbox for unit tests/demos (runs NOTHING).

    ``script`` maps (tuple(command), stdin_data) -> SandboxResult. Unmapped
    calls return ``default``. Used so tests never need Docker or the host
    interpreter.
    """

    default: SandboxResult = field(
        default_factory=lambda: SandboxResult(
            stdout="", stderr="", exit_code=0, timed_out=False, time_ms=1
        )
    )
    calls: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._script: dict[tuple[tuple[str, ...], str], SandboxResult] = {}

    def program(
        self, command: list[str], stdin_data: str, result: SandboxResult
    ) -> "FakeSandboxRunner":
        self._script[(tuple(command), stdin_data)] = result
        return self

    def run(self, files, command, stdin_data, timeout_seconds):
        self.calls.append(
            {
                "files": dict(files),
                "command": list(command),
                "stdin_data": stdin_data,
                "timeout_seconds": timeout_seconds,
            }
        )
        key = (tuple(command), stdin_data)
        if key in self._script:
            return self._script[key]
        # Fallback: match on command only (any stdin).
        for (cmd, _stdin), result in self._script.items():
            if cmd == tuple(command):
                return result
        return self.default


__all__ = [
    "CONTAINER_WORKDIR",
    "DEFAULT_CPUS",
    "DEFAULT_MEMORY",
    "DEFAULT_PIDS_LIMIT",
    "DockerSandboxRunner",
    "FakeSandboxRunner",
    "RunResult",
    "SandboxResult",
    "SandboxRunner",
    "SandboxUnavailableError",
    "docker_available",
]
