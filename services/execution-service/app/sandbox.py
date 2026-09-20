"""COGNIFY execution-service — isolated Docker sandbox.

Security contract:
- Student code NEVER runs on the host.
- The only subprocesses target the Docker CLI.
- No shell=True / eval / exec / compile / os.system.
- Sandbox containers use --network none.
- Memory, CPU and PID limits are always applied.
- No host environment variables are forwarded.
- Docker unavailable => fail closed.
- Output is bounded to prevent memory exhaustion.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MEMORY: str = "256m"
DEFAULT_CPUS: str = "1.0"
DEFAULT_PIDS_LIMIT: int = 128
CONTAINER_WORKDIR: str = "/workspace"
MAX_STDOUT_CHARS: int = 50_000
MAX_STDERR_CHARS: int = 10_000

# Used only to copy source files into a Docker-managed volume.
# This container NEVER executes student code.
WORKSPACE_HELPER_IMAGE: str = "python:3.11-slim"
WORKSPACE_SETUP_TIMEOUT: float = 30.0


class SandboxUnavailableError(RuntimeError):
    """Raised when Docker is unavailable or sandbox setup fails."""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[truncated {len(text) - limit} chars]"


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
    """Abstraction over an isolated backend."""

    @abstractmethod
    def run(
        self,
        files: dict[str, str],
        command: list[str],
        stdin_data: str,
        timeout_seconds: float,
    ) -> SandboxResult:
        """Run command in isolation with files mounted at /workspace."""
        raise NotImplementedError


def docker_available(docker_bin: str = "docker") -> bool:
    """True iff Docker CLI exists and the Docker daemon responds."""
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
    """Execute student programs inside isolated Docker containers.

    A Docker-managed named volume is used instead of a host bind mount.

    Why:
        The execution service itself runs inside Docker, while the Docker
        daemon runs outside that container. A path such as /cognify-exec
        inside the execution-service container is therefore not automatically
        visible to the Docker daemon.

    Workflow:
        1. Validate filenames.
        2. Create/populate a temporary Docker volume using a fixed helper.
        3. Run the student's command against that volume.
        4. Remove the temporary volume.
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

        # Kept for backwards compatibility with the previous constructor.
        # Named Docker volumes no longer use this path.
        self.workdir_base = workdir_base

    def build_command(
        self,
        volume_name: str,
        container_name: str,
    ) -> list[str]:
        """Build the student-container Docker argv.

        No environment forwarding flags are ever added here.
        """
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
            f"{volume_name}:{CONTAINER_WORKDIR}",
            "-w",
            CONTAINER_WORKDIR,
            "-i",
            self.image,
        ]

    def _validate_files(self, files: dict[str, str]) -> None:
        """Reject path traversal and absolute paths before Docker is invoked."""
        for name, content in files.items():
            if not isinstance(name, str) or not name:
                raise ValueError("File name must be a non-empty string.")

            if not isinstance(content, str):
                raise ValueError(
                    f"File content for {name!r} must be a string."
                )

            path = Path(name)

            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe file name {name!r}.")

    def _populate_volume(
        self,
        volume_name: str,
        files: dict[str, str],
        helper_name: str,
    ) -> None:
        """Write source files into a Docker-managed volume.

        The helper receives source text as JSON and ONLY writes files.
        It does not execute student code.
        """
        payload = json.dumps(
            files,
            ensure_ascii=False,
        ).encode("utf-8")

        helper_script = (
            "import json\n"
            "from pathlib import Path\n"
            "import sys\n"
            "\n"
            "root = Path('/workspace')\n"
            "files = json.load(sys.stdin)\n"
            "\n"
            "for name, content in files.items():\n"
            "    target = root / name\n"
            "    target.parent.mkdir(parents=True, exist_ok=True)\n"
            "    target.write_text(content, encoding='utf-8')\n"
        )

        argv = [
            self.docker_bin,
            "run",
            "--rm",
            "--name",
            helper_name,
            "--network",
            "none",
            "--memory",
            self.memory,
            "--memory-swap",
            self.memory,
            "--cpus",
            self.cpus,
            "--pids-limit",
            str(self.pids_limit),
            "-v",
            f"{volume_name}:{CONTAINER_WORKDIR}",
            "-w",
            CONTAINER_WORKDIR,
            "-i",
            WORKSPACE_HELPER_IMAGE,
            "python",
            "-c",
            helper_script,
        ]

        try:
            proc = subprocess.run(
                argv,
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=WORKSPACE_SETUP_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            self._kill_container(helper_name)
            raise SandboxUnavailableError(
                "Sandbox workspace setup timed out."
            ) from None
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxUnavailableError(
                f"Sandbox workspace setup failed: {exc}"
            ) from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()

            raise SandboxUnavailableError(
                "Sandbox workspace setup failed"
                + (f": {stderr}" if stderr else ".")
            )

    def _remove_volume(self, volume_name: str) -> None:
        """Best-effort removal of the temporary Docker volume."""
        try:
            subprocess.run(
                [
                    self.docker_bin,
                    "volume",
                    "rm",
                    volume_name,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def run(
        self,
        files: dict[str, str],
        command: list[str],
        stdin_data: str,
        timeout_seconds: float,
    ) -> SandboxResult:
        if not docker_available(self.docker_bin):
            raise SandboxUnavailableError(
                "Docker is unavailable; refusing to execute "
                "student code on the host."
            )

        if not command:
            raise ValueError("command must be a non-empty argv list.")

        self._validate_files(files)

        volume_name = f"cognify-exec-vol-{uuid.uuid4().hex[:12]}"
        container_name = f"cognify-exec-{uuid.uuid4().hex[:12]}"
        helper_name = f"cognify-workspace-{uuid.uuid4().hex[:12]}"

        try:
            # Docker automatically creates the named volume when the helper
            # mounts it for the first time.
            self._populate_volume(
                volume_name,
                files,
                helper_name,
            )

            argv = self.build_command(
                volume_name,
                container_name,
            ) + list(command)

            start = time.monotonic()

            try:
                proc = subprocess.run(
                    argv,
                    input=stdin_data.encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_seconds,
                )

                elapsed_ms = int(
                    (time.monotonic() - start) * 1000
                )

                stdout = proc.stdout.decode(
                    "utf-8",
                    errors="replace",
                )
                stderr = proc.stderr.decode(
                    "utf-8",
                    errors="replace",
                )

                return SandboxResult(
                    stdout=_truncate(stdout, MAX_STDOUT_CHARS),
                    stderr=_truncate(stderr, MAX_STDERR_CHARS),
                    exit_code=proc.returncode,
                    timed_out=False,
                    time_ms=elapsed_ms,
                )

            except subprocess.TimeoutExpired as exc:
                elapsed_ms = int(
                    (time.monotonic() - start) * 1000
                )

                self._kill_container(container_name)

                partial = b"".join(
                    chunk
                    for chunk in (exc.stdout, exc.stderr)
                    if chunk
                )

                partial_text = (
                    partial.decode(
                        "utf-8",
                        errors="replace",
                    )
                    if partial
                    else ""
                )

                return SandboxResult(
                    stdout="",
                    stderr=_truncate(
                        (
                            partial_text + "\n"
                            if partial_text
                            else ""
                        )
                        + f"TIMEOUT: exceeded "
                        f"{timeout_seconds}s wall-clock limit.",
                        MAX_STDERR_CHARS,
                    ),
                    exit_code=-1,
                    timed_out=True,
                    time_ms=elapsed_ms,
                )

        finally:
            self._remove_volume(volume_name)

    def _kill_container(self, container_name: str) -> None:
        """Best-effort cleanup for timed-out containers."""
        try:
            subprocess.run(
                [
                    self.docker_bin,
                    "kill",
                    container_name,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass


@dataclass
class FakeSandboxRunner(SandboxRunner):
    """Scripted in-memory sandbox for unit tests/demos."""

    default: SandboxResult = field(
        default_factory=lambda: SandboxResult(
            stdout="",
            stderr="",
            exit_code=0,
            timed_out=False,
            time_ms=1,
        )
    )

    calls: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._script: dict[
            tuple[tuple[str, ...], str],
            SandboxResult,
        ] = {}

    def program(
        self,
        command: list[str],
        stdin_data: str,
        result: SandboxResult,
    ) -> "FakeSandboxRunner":
        self._script[
            (tuple(command), stdin_data)
        ] = result
        return self

    def run(
        self,
        files,
        command,
        stdin_data,
        timeout_seconds,
    ):
        self.calls.append(
            {
                "files": dict(files),
                "command": list(command),
                "stdin_data": stdin_data,
                "timeout_seconds": timeout_seconds,
            }
        )

        key = (
            tuple(command),
            stdin_data,
        )

        if key in self._script:
            return self._script[key]

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
    "MAX_STDOUT_CHARS",
    "MAX_STDERR_CHARS",
]