"""Unit tests for Step 5: code execution + test evaluation (execution-service).

All execution is MOCKED (FakeSandboxRunner / scripted FakeRunner): no Docker,
no host interpreter, no Java toolchain needed. Docker-dependent behavior
(command construction, isolation flags, timeout mapping) is verified by
mocking ``subprocess.run``.

Run from repo root:
    python -m unittest discover -s services/execution-service/tests -t . -v

NOTE: ``services/execution-service`` is not an importable package name
(hyphen), so this file bootstraps ``sys.path`` with the repo root AND the
service dir, then imports ``app.*`` plus ``packages.problem_schema``.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# -- sys.path bootstrap (repo root + service dir) ---------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
_SERVICE_DIR = _ROOT / "services" / "execution-service"
for _p in (str(_ROOT), str(_SERVICE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi.testclient import TestClient  # noqa: E402

from app.evaluator import evaluate, normalize_output  # noqa: E402
from app.java_runner import (  # noqa: E402
    CLASS_NAME,
    COMPILE_COMMAND,
    JAVA_IMAGE,
    SOURCE_FILENAME as JAVA_SOURCE,
    JavaRunner,
)
from app.java_runner import RUN_COMMAND as JAVA_RUN_COMMAND
from app.main import create_app, default_runner_factory  # noqa: E402
from app.models import (  # noqa: E402
    ExecutionRequest,
    ExecutionStatus,
)
from app.python_runner import (  # noqa: E402
    PYTHON_IMAGE,
    SOLUTION_FILENAME,
    PythonRunner,
)
from app.python_runner import RUN_COMMAND as PY_RUN_COMMAND
from app.runners import BaseRunner  # noqa: E402
from app.sandbox import (  # noqa: E402
    DockerSandboxRunner,
    FakeSandboxRunner,
    RunResult,
    SandboxResult,
    SandboxUnavailableError,
    docker_available,
)
from packages.problem_schema import TestCase  # noqa: E402

_PY_OK = "print(sum(int(x) for x in input().split()))"
_JAVA_OK = (
    "import java.util.*;\npublic class Main {\n"
    " public static void main(String[] a) {\n"
    "  Scanner s = new Scanner(System.in);\n"
    "  int t = 0; while (s.hasNextInt()) t += s.nextInt();\n"
    "  System.out.println(t);\n }\n}\n"
)


def _cases(*specs: tuple[str, str, str]) -> list[TestCase]:
    return [TestCase(id=i, input=j, expected_output=k) for i, j, k in specs]


def _ok_run(stdout: str, time_ms: int = 12) -> RunResult:
    return RunResult(
        stdout=stdout, stderr="", exit_code=0, timed_out=False, time_ms=time_ms
    )


class FakeRunner(BaseRunner):
    """Scripted runner: canned RunResult per stdin, optional compile failure."""

    def __init__(
        self,
        language: str,
        runs: dict[str, RunResult] | None = None,
        compile_failure: str | None = None,
    ) -> None:
        super().__init__(FakeSandboxRunner())
        self.language = language
        self._runs = runs or {}
        self._compile_failure = compile_failure
        self.compile_calls: list[str] = []
        self.run_calls: list[str] = []

    def compile(self, code: str, timeout_seconds: float) -> str | None:
        self.compile_calls.append(code)
        return self._compile_failure

    def run_single(
        self, code: str, stdin_data: str, timeout_seconds: float
    ) -> RunResult:
        self.run_calls.append(stdin_data)
        return self._runs.get(
            stdin_data, _ok_run(stdin_data, 5)
        )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ExecutionStatusTests(unittest.TestCase):
    def test_all_five_statuses_exist(self):
        self.assertEqual(
            {s.value for s in ExecutionStatus},
            {"PASSED", "FAILED", "COMPILE_ERROR", "RUNTIME_ERROR", "TIMEOUT"},
        )


class ExecutionRequestTests(unittest.TestCase):
    def test_valid_request_normalizes_language(self):
        req = ExecutionRequest(
            language=" Python ",
            code=_PY_OK,
            tests=[{"id": "t1", "input": "1 2", "expected_output": "3"}],
        )
        self.assertEqual(req.language, "python")
        cases = req.to_test_cases()
        self.assertEqual(len(cases), 1)
        self.assertIsInstance(cases[0], TestCase)
        self.assertEqual(cases[0].expected_output, "3")

    def test_rejects_unknown_language(self):
        with self.assertRaises(Exception):
            ExecutionRequest(
                language="c++", code="x", tests=[{"id": "t1"}]
            )

    def test_rejects_empty_code_and_bad_tests(self):
        with self.assertRaises(Exception):
            ExecutionRequest(language="python", code="   ", tests=[{"id": "t1"}])
        with self.assertRaises(Exception):
            ExecutionRequest(language="python", code="x", tests=[])
        with self.assertRaises(Exception):  # duplicate/invalid ids surface via TestCase
            ExecutionRequest(
                language="python", code="x", tests=[{"id": "bad id!"}]
            ).to_test_cases()

    def test_rejects_timeout_out_of_bounds(self):
        good = {"language": "python", "code": "x", "tests": [{"id": "t1"}]}
        with self.assertRaises(Exception):
            ExecutionRequest(**{**good, "timeout_seconds": 0.1})
        with self.assertRaises(Exception):
            ExecutionRequest(**{**good, "timeout_seconds": 999})

    def test_rejects_oversized_code(self):
        with self.assertRaises(Exception):
            ExecutionRequest(
                language="python",
                code="x" * 100_001,
                tests=[{"id": "t1"}],
            )


# ---------------------------------------------------------------------------
# Output normalization
# ---------------------------------------------------------------------------
class NormalizeOutputTests(unittest.TestCase):
    def test_trims_and_normalizes_crlf(self):
        self.assertEqual(normalize_output("3\r\n"), "3")
        self.assertEqual(normalize_output("  a  \n  b  \n"), "a\n  b")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            normalize_output(3)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Evaluator (mocked runners — no Docker, no host execution)
# ---------------------------------------------------------------------------
class EvaluatorTests(unittest.TestCase):
    def test_passed_all_tests(self):
        runner = FakeRunner(
            "python",
            runs={"1 2": _ok_run("3\n"), "4 5": _ok_run("9\n")},
        )
        result = evaluate(
            "python", _PY_OK, _cases(("t1", "1 2", "3"), ("t2", "4 5", "9")), runner
        )
        self.assertEqual(result.status, ExecutionStatus.PASSED)
        self.assertEqual(result.language, "python")
        self.assertEqual((result.passed_count, result.failed_count), (2, 0))
        self.assertIsNone(result.failed_test_id)
        self.assertEqual(result.execution_time_ms, 24)
        self.assertTrue(all(t.passed for t in result.tests))

    def test_failed_captures_expected_and_actual(self):
        runner = FakeRunner("python", runs={"1 2": _ok_run("4\n")})
        result = evaluate("python", _PY_OK, _cases(("t1", "1 2", "3")), runner)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failed_test_id, "t1")
        self.assertEqual(result.expected_output, "3")
        self.assertEqual(result.actual_output, "4\n")
        self.assertEqual(result.stdout, "4\n")
        self.assertEqual(result.failed_count, 1)

    def test_first_failure_is_decisive(self):
        runner = FakeRunner(
            "python", runs={"a": _ok_run("WRONG"), "b": _ok_run("ALSO WRONG")}
        )
        result = evaluate(
            "python", _PY_OK, _cases(("t1", "a", "1"), ("t2", "b", "2")), runner
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.failed_test_id, "t1")
        self.assertEqual(result.expected_output, "1")

    def test_runtime_error_on_nonzero_exit(self):
        runner = FakeRunner(
            "python",
            runs={
                "x": RunResult(
                    stdout="",
                    stderr="Traceback: ZeroDivisionError",
                    exit_code=1,
                    timed_out=False,
                    time_ms=7,
                )
            },
        )
        result = evaluate("python", _PY_OK, _cases(("t1", "x", "0")), runner)
        self.assertEqual(result.status, ExecutionStatus.RUNTIME_ERROR)
        self.assertEqual(result.stderr, "Traceback: ZeroDivisionError")
        self.assertEqual(result.failed_test_id, "t1")

    def test_timeout_status_when_any_test_times_out(self):
        runner = FakeRunner(
            "python",
            runs={
                "slow": RunResult(
                    stdout="", stderr="", exit_code=-1, timed_out=True, time_ms=5000
                )
            },
        )
        result = evaluate("python", _PY_OK, _cases(("t1", "slow", "0")), runner)
        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)
        self.assertTrue(result.tests[0].timed_out)

    def test_compile_error_short_circuits(self):
        runner = FakeRunner("java", compile_failure="Main.java:3: ';' expected")
        result = evaluate("java", _JAVA_OK, _cases(("t1", "1", "1")), runner)
        self.assertEqual(result.status, ExecutionStatus.COMPILE_ERROR)
        self.assertEqual(result.stderr, "Main.java:3: ';' expected")
        self.assertEqual(result.tests, [])
        self.assertEqual(runner.run_calls, [])  # no tests executed after failure

    def test_status_precedence_timeout_over_runtime_over_failed(self):
        runner = FakeRunner(
            "python",
            runs={
                "t": RunResult("", "", -1, True, 5),
                "r": RunResult("", "boom", 1, False, 5),
                "f": _ok_run("wrong"),
            },
        )
        cases = _cases(("t1", "t", "0"), ("t2", "r", "0"), ("t3", "f", "0"))
        result = evaluate("python", _PY_OK, cases, runner)
        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)

        runner2 = FakeRunner(
            "python",
            runs={"r": RunResult("", "boom", 1, False, 5), "f": _ok_run("wrong")},
        )
        result2 = evaluate("python", _PY_OK, _cases(("t2", "r", "0"), ("t3", "f", "0")), runner2)
        self.assertEqual(result2.status, ExecutionStatus.RUNTIME_ERROR)

    def test_rejects_runner_language_mismatch(self):
        runner = FakeRunner("python")
        with self.assertRaises(ValueError):
            evaluate("java", _JAVA_OK, _cases(("t1", "", "")), runner)

    def test_rejects_empty_cases_and_bad_inputs(self):
        runner = FakeRunner("python")
        with self.assertRaises(ValueError):
            evaluate("python", _PY_OK, [], runner)
        with self.assertRaises(ValueError):
            evaluate("python", "   ", _cases(("t1", "", "")), runner)
        with self.assertRaises(TypeError):
            evaluate("python", _PY_OK, [{"id": "t1"}], runner)  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Runners (FakeSandbox — asserts wiring, files, commands)
# ---------------------------------------------------------------------------
class PythonRunnerTests(unittest.TestCase):
    def test_writes_solution_file_and_runs(self):
        sandbox = FakeSandboxRunner(
            default=SandboxResult("3\n", "", 0, False, 9)
        )
        runner = PythonRunner(sandbox=sandbox)
        self.assertEqual(runner.language, "python")
        out = runner.run_single(_PY_OK, "1 2", 5.0)
        self.assertEqual((out.stdout, out.exit_code, out.timed_out), ("3\n", 0, False))
        call = sandbox.calls[0]
        self.assertEqual(call["files"], {SOLUTION_FILENAME: _PY_OK})
        self.assertEqual(call["command"], PY_RUN_COMMAND)
        self.assertEqual(call["stdin_data"], "1 2")
        self.assertEqual(call["timeout_seconds"], 5.0)

    def test_maps_sandbox_timeout(self):
        sandbox = FakeSandboxRunner(
            default=SandboxResult("", "TIMEOUT", -1, True, 5000)
        )
        out = PythonRunner(sandbox=sandbox).run_single(_PY_OK, "", 1.0)
        self.assertTrue(out.timed_out)

    def test_default_image_and_no_compile_step(self):
        self.assertEqual(PYTHON_IMAGE, "python:3.11-slim")
        runner = PythonRunner(sandbox=FakeSandboxRunner())
        self.assertIsNone(runner.compile(_PY_OK, 5.0))


class JavaRunnerTests(unittest.TestCase):
    def test_compile_success_then_run(self):
        sandbox = FakeSandboxRunner()
        sandbox.program(
            COMPILE_COMMAND, "", SandboxResult("", "", 0, False, 100)
        ).program(
            JAVA_RUN_COMMAND, "1 2", SandboxResult("3\n", "", 0, False, 40)
        )
        runner = JavaRunner(sandbox=sandbox)
        self.assertEqual(runner.language, "java")
        self.assertIsNone(runner.compile(_JAVA_OK, 5.0))
        out = runner.run_single(_JAVA_OK, "1 2", 5.0)
        self.assertEqual(out.stdout, "3\n")
        compile_call, run_call = sandbox.calls
        self.assertEqual(compile_call["files"], {JAVA_SOURCE: _JAVA_OK})
        self.assertEqual(compile_call["command"], COMPILE_COMMAND)
        self.assertEqual(run_call["files"], {JAVA_SOURCE: _JAVA_OK})
        self.assertEqual(run_call["command"], JAVA_RUN_COMMAND)

    def test_compile_failure_message(self):
        sandbox = FakeSandboxRunner(
            default=SandboxResult("", "Main.java:1: error: ...", 1, False, 50)
        )
        err = JavaRunner(sandbox=sandbox).compile("broken java", 5.0)
        self.assertIn("Main.java", err)

    def test_class_and_image_convention(self):
        self.assertEqual((JAVA_SOURCE, CLASS_NAME), ("Main.java", "Main"))
        self.assertIn("17", JAVA_IMAGE)


# ---------------------------------------------------------------------------
# Sandbox (mocked subprocess — asserts isolation flags)
# ---------------------------------------------------------------------------
class DockerSandboxTests(unittest.TestCase):
    def test_build_command_has_isolation_and_no_env_flags(self):
        runner = DockerSandboxRunner(image="python:3.11-slim")
        argv = runner.build_command("/tmp/x", "cognify-exec-abc")
        for flag in ("--rm", "--network", "none", "--memory", "256m",
                     "--cpus", "1.0", "--pids-limit", "128"):
            self.assertIn(flag, argv)
        for forbidden in ("-e", "--env", "--env-file"):
            self.assertNotIn(forbidden, argv)
        self.assertEqual(argv[0], "docker")

    def test_run_uses_docker_and_returns_output(self):
        completed = subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=b"3\n",
            stderr=b"",
        )

        with patch(
            "app.sandbox.docker_available",
            return_value=True,
        ), patch(
            "app.sandbox.subprocess.run",
            side_effect=[
                completed,  # workspace helper
                completed,  # student container
                completed,  # volume cleanup
            ],
        ) as mock_run:
            runner = DockerSandboxRunner(
                image="python:3.11-slim"
            )

            result = runner.run(
                {"solution.py": "x"},
                ["python", "/workspace/solution.py"],
                "1",
                5.0,
            )

        self.assertEqual(
            (
                result.stdout,
                result.exit_code,
                result.timed_out,
            ),
            ("3\n", 0, False),
        )

        self.assertEqual(mock_run.call_count, 3)

        helper_argv = mock_run.call_args_list[0].args[0]
        student_argv = mock_run.call_args_list[1].args[0]
        cleanup_argv = mock_run.call_args_list[2].args[0]

        self.assertEqual(helper_argv[0], "docker")
        self.assertEqual(student_argv[0], "docker")
        self.assertEqual(
            cleanup_argv[:3],
            ["docker", "volume", "rm"],
        )

        self.assertNotIn(
            "shell",
            mock_run.call_args_list[1].kwargs,
        )

        self.assertEqual(
            mock_run.call_args_list[1].kwargs["timeout"],
            5.0,
        )

        self.assertEqual(
            mock_run.call_args_list[1].kwargs["input"],
            b"1",
        )
    def test_timeout_maps_and_kills_container(self):
        completed = subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

        timeout_error = subprocess.TimeoutExpired(
            cmd=["docker", "run"],
            timeout=5.0,
            output=b"part",
        )

        with patch(
            "app.sandbox.docker_available",
            return_value=True,
        ), patch(
            "app.sandbox.subprocess.run",
            side_effect=[
                completed,       # workspace helper
                timeout_error,  # student container
                completed,       # volume cleanup
            ],
        ) as mock_run, patch.object(
            DockerSandboxRunner,
            "_kill_container",
            return_value=None,
        ) as mock_kill:
            result = DockerSandboxRunner(
                image="img"
            ).run(
                {"f": "x"},
                ["cmd"],
                "",
                5.0,
            )

        self.assertTrue(result.timed_out)
        self.assertIn("TIMEOUT", result.stderr)
        mock_kill.assert_called_once()
        self.assertEqual(mock_run.call_count, 3)
    def test_fail_closed_without_docker(self):
        with patch("app.sandbox.docker_available", return_value=False):
            with self.assertRaises(SandboxUnavailableError):
                DockerSandboxRunner(image="img").run({"f": "x"}, ["cmd"], "", 5.0)

    def test_docker_available_false_without_binary(self):
        with patch("app.sandbox.shutil.which", return_value=None):
            self.assertFalse(docker_available("docker"))

    def test_rejects_unsafe_filenames(self):
        with patch("app.sandbox.docker_available", return_value=True):
            with self.assertRaises(ValueError):
                DockerSandboxRunner(image="img").run(
                    {"../evil.py": "x"}, ["cmd"], "", 5.0
                )


# ---------------------------------------------------------------------------
# Security static checks
# ---------------------------------------------------------------------------
class SecurityTests(unittest.TestCase):
    """Static guarantees via AST (docstrings/comments are not code)."""

    def _trees(self) -> dict[str, object]:
        import ast

        app_dir = _SERVICE_DIR / "app"
        return {
            p.name: ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
            for p in sorted(app_dir.glob("*.py"))
        }

    def test_no_host_execution_primitives(self):
        import ast

        for name, tree in self._trees().items():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name) and func.id in {"eval", "exec", "compile"}:
                    self.fail(f"{name}: forbidden call to {func.id}()")
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "system"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                ):
                    self.fail(f"{name}: forbidden os.system() call")
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        self.assertNotEqual(kw.value.value, True, f"{name}: shell=True")
        # Only sandbox.py may touch subprocess, and only for the docker CLI.
        for name in self._trees():
            src = (_SERVICE_DIR / "app" / name).read_text(encoding="utf-8")
            if name == "sandbox.py":
                self.assertIn("docker", src)
            else:
                self.assertNotIn("subprocess", src, name)

    def test_no_env_forwarding_into_containers(self):
        import ast

        for name, tree in self._trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in {
                    "environ",
                    "getenv",
                    "getenvb",
                }:
                    self.fail(f"{name}: host env access is forbidden")
        # Isolation flags live in exactly one place (covered behaviorally by
        # DockerSandboxTests.test_build_command_has_isolation_and_no_env_flags).
        sandbox_src = (_SERVICE_DIR / "app" / "sandbox.py").read_text(encoding="utf-8")
        self.assertIn('"--network"', sandbox_src)


# ---------------------------------------------------------------------------
# API (TestClient + injected fake runners — no Docker)
# ---------------------------------------------------------------------------
def _api_app() -> TestClient:
    def factory(language: str, timeout: float) -> BaseRunner:
        if language == "python":
            return FakeRunner("python", runs={"1 2": _ok_run("3\n")})
        if language == "java":
            return FakeRunner("java", runs={"1 2": _ok_run("3\n")})
        raise ValueError(f"Unsupported language {language!r}.")

    return TestClient(create_app(runner_factory=factory))


class ExecutionApiTests(unittest.TestCase):
    def test_health_and_languages(self):
        client = _api_app()
        self.assertEqual(client.get("/health").json()["status"], "ok")
        self.assertEqual(
            set(client.get("/languages").json()["languages"]), {"python", "java"}
        )

    def test_execute_python_passed(self):
        client = _api_app()
        resp = client.post(
            "/execute",
            json={
                "language": "python",
                "code": _PY_OK,
                "tests": [{"id": "t1", "input": "1 2", "expected_output": "3"}],
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "PASSED")
        self.assertEqual(body["language"], "python")
        self.assertIn("execution_time_ms", body)
        self.assertEqual(body["tests"][0]["test_id"], "t1")
        for key in ("stdout", "stderr", "failed_test_id", "expected_output",
                    "actual_output", "execution_time_ms", "language", "status"):
            self.assertIn(key, body)

    def test_execute_java_passed(self):
        client = _api_app()
        resp = client.post(
            "/execute",
            json={
                "language": "java",
                "code": _JAVA_OK,
                "tests": [{"id": "t1", "input": "1 2", "expected_output": "3"}],
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["status"], "PASSED")

    def test_execute_failure_surfaces_failed_test(self):
        def factory(language: str, timeout: float) -> BaseRunner:
            return FakeRunner("python", runs={"1 2": _ok_run("999\n")})

        client = TestClient(create_app(runner_factory=factory))
        resp = client.post(
            "/execute",
            json={
                "language": "python",
                "code": _PY_OK,
                "tests": [{"id": "t1", "input": "1 2", "expected_output": "3"}],
            },
        )
        body = resp.json()
        self.assertEqual(body["status"], "FAILED")
        self.assertEqual(body["failed_test_id"], "t1")
        self.assertEqual(body["expected_output"], "3")
        self.assertEqual(body["actual_output"], "999\n")

    def test_execute_compile_error(self):
        def factory(language: str, timeout: float) -> BaseRunner:
            return FakeRunner("java", compile_failure="Main.java:3: ';' expected")

        client = TestClient(create_app(runner_factory=factory))
        resp = client.post(
            "/execute",
            json={
                "language": "java",
                "code": "broken",
                "tests": [{"id": "t1", "input": "", "expected_output": ""}],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "COMPILE_ERROR")

    def test_sandbox_unavailable_maps_to_503(self):
        class _Down(BaseRunner):
            language = "python"

            def run_single(self, code, stdin_data, timeout_seconds):
                raise SandboxUnavailableError("no docker")

        client = TestClient(
            create_app(runner_factory=lambda lang, t: _Down(FakeSandboxRunner()))
        )
        resp = client.post(
            "/execute",
            json={"language": "python", "code": "x", "tests": [{"id": "t1"}]},
        )
        self.assertEqual(resp.status_code, 503)

    def test_invalid_payload_rejected(self):
        client = _api_app()
        resp = client.post(
            "/execute",
            json={"language": "ruby", "code": "x", "tests": [{"id": "t1"}]},
        )
        self.assertEqual(resp.status_code, 422)
        resp2 = client.post(
            "/execute",
            json={"language": "python", "code": "   ", "tests": [{"id": "t1"}]},
        )
        self.assertEqual(resp2.status_code, 422)

    def test_default_runner_factory_dispatch(self):
        self.assertIsInstance(default_runner_factory("python", 5.0), PythonRunner)
        self.assertIsInstance(default_runner_factory("java", 5.0), JavaRunner)
        with self.assertRaises(ValueError):
            default_runner_factory("ruby", 5.0)


if __name__ == "__main__":
    unittest.main()
