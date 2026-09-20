"""Focused tests for the core-backend -> execution-service HTTP integration.

Production bug: core-backend instantiated DockerSandboxRunner locally
(no Docker in core-backend) -> POST /student/submissions returned 503.
Fix: production path POSTs EXECUTION_SERVICE_URL/execute and returns the
validated ExecutionResult dict (existing pipeline contract).

Covers:
  A. adapter sends correct language/code/tests/timeout payload
  B. PASSED response converts into the pipeline execution contract
  C. FAILED response preserves failed_test_id/expected/actual + per-test
  D. connection failure becomes HTTP 503 (never a crash, never local exec)
  E. submission no longer tries to instantiate DockerSandboxRunner
  F. existing runner_factory injection still works (covered by existing
     suite; spot-checked here that injected path never touches HTTP)

Run from repo root:
    python -m unittest discover -s services/core-backend/tests -t . -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
_SERVICE_DIR = _ROOT / "services" / "core-backend"
for _p in (str(_ROOT), str(_SERVICE_DIR), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from packages.problem_bank import loader as bank_loader  # noqa: E402
from packages.problem_bank import pipeline as pipe  # noqa: E402

from app import execution_client  # noqa: E402
from app import student as student_mod  # noqa: E402
from app.main import create_app  # noqa: E402

CANONICAL_ID = "PY-C3-COUNT-DIV"
TIMEOUT = 5.0


def _passed_response(problem, time_ms: int = 5) -> dict:
    tests = []
    for case in problem.all_tests():
        tests.append(
            {
                "test_id": case.id,
                "passed": True,
                "input": case.input,
                "expected_output": case.expected_output,
                "actual_output": case.expected_output,
                "stdout": case.expected_output + "\n",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "time_ms": time_ms,
            }
        )
    first = tests[0]
    return {
        "status": "PASSED",
        "language": problem.language,
        "execution_time_ms": sum(t["time_ms"] for t in tests),
        "stdout": first["stdout"],
        "stderr": first["stderr"],
        "tests": tests,
        "passed_count": len(tests),
        "failed_count": 0,
        "failed_test_id": None,
        "expected_output": None,
        "actual_output": None,
    }


def _failed_response(problem, fail_index: int = 2) -> dict:
    tests = []
    cases = list(problem.all_tests())
    for i, case in enumerate(cases):
        if i < fail_index:
            tests.append(
                {
                    "test_id": case.id,
                    "passed": True,
                    "input": case.input,
                    "expected_output": case.expected_output,
                    "actual_output": case.expected_output,
                    "stdout": case.expected_output + "\n",
                    "stderr": "",
                    "exit_code": 0,
                    "timed_out": False,
                    "time_ms": 5,
                }
            )
        elif i == fail_index:
            tests.append(
                {
                    "test_id": case.id,
                    "passed": False,
                    "input": case.input,
                    "expected_output": case.expected_output,
                    "actual_output": "WRONG\n",
                    "stdout": "WRONG\n",
                    "stderr": "",
                    "exit_code": 0,
                    "timed_out": False,
                    "time_ms": 5,
                }
            )
        else:
            tests.append(
                {
                    "test_id": case.id,
                    "passed": False,
                    "input": case.input,
                    "expected_output": case.expected_output,
                    "actual_output": "WRONG\n",
                    "stdout": "WRONG\n",
                    "stderr": "",
                    "exit_code": 0,
                    "timed_out": False,
                    "time_ms": 5,
                }
            )
    decisive = tests[fail_index]
    passed = sum(1 for t in tests if t["passed"])
    failed = len(tests) - passed
    return {
        "status": "FAILED",
        "language": problem.language,
        "execution_time_ms": sum(t["time_ms"] for t in tests),
        "stdout": decisive["stdout"],
        "stderr": decisive["stderr"],
        "tests": tests,
        "passed_count": passed,
        "failed_count": failed,
        "failed_test_id": decisive["test_id"],
        "expected_output": decisive["expected_output"],
        "actual_output": decisive["actual_output"],
    }


class _FakeHttpResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class PayloadTests(unittest.TestCase):
    def test_adapter_sends_correct_payload(self):
        """A: language/code/tests/timeout shape matches POST /execute."""
        import httpx

        problem = bank_loader.load_problem(CANONICAL_ID)
        code = "def count_divisible(nums, k):\n    return 0\n"
        captured: dict = {}

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return _FakeHttpResponse(200, _passed_response(problem))

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            execution_client.execute_problem(
                problem, code, timeout_seconds=TIMEOUT
            )
        self.assertTrue(captured["url"].endswith("/execute"))
        payload = captured["json"]
        self.assertEqual(payload["language"], "python")
        self.assertEqual(payload["code"], code)
        self.assertEqual(payload["timeout_seconds"], TIMEOUT)
        self.assertEqual(len(payload["tests"]), len(list(problem.all_tests())))
        for sent, case in zip(payload["tests"], problem.all_tests()):
            self.assertEqual(sent["id"], case.id)
            self.assertEqual(sent["input"], case.input)
            self.assertEqual(sent["expected_output"], case.expected_output)

    def test_build_payload_is_pure_and_complete(self):
        problem = bank_loader.load_problem(CANONICAL_ID)
        payload = execution_client.build_payload(problem, "x=1\n", 5.0)
        self.assertEqual(
            set(payload), {"language", "code", "tests", "timeout_seconds"}
        )


class ContractTests(unittest.TestCase):
    def test_passed_response_converts_to_pipeline_contract(self):
        """B: PASSED dict works with all downstream pipeline helpers."""
        import httpx

        problem = bank_loader.load_problem(CANONICAL_ID)
        expected = _passed_response(problem)

        def fake_post(url, json=None, timeout=None):
            return _FakeHttpResponse(200, expected)

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            result = execution_client.execute_problem(
                problem, "x=1\n", timeout_seconds=TIMEOUT
            )
        self.assertEqual(pipe.execution_status_str(result), "PASSED")
        view = pipe.to_student_view(problem, result)
        self.assertEqual(view["passed_count"], len(list(problem.all_tests())))
        self.assertEqual(view["failed_count"], 0)
        snapshot = pipe.default_learner_snapshot(problem)
        pack = pipe.build_pack_for_submission("x=1\n", problem, result, snapshot)
        self.assertEqual(pack.execution_status, "PASSED")
        attempt = pipe.attempt_from_execution(problem, result)
        self.assertTrue(attempt.passed)

    def test_failed_response_preserves_failure_details(self):
        """C: FAILED preserves failed_test_id/expected/actual + per-test."""
        problem = bank_loader.load_problem(CANONICAL_ID)
        expected = _failed_response(problem, fail_index=2)

        def fake_post(url, json=None, timeout=None):
            return _FakeHttpResponse(200, expected)

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            result = execution_client.execute_problem(
                problem, "x=1\n", timeout_seconds=TIMEOUT
            )
        self.assertEqual(pipe.execution_status_str(result), "FAILED")
        self.assertEqual(result["failed_test_id"], expected["failed_test_id"])
        self.assertEqual(result["expected_output"], expected["expected_output"])
        self.assertEqual(result["actual_output"], expected["actual_output"])
        self.assertEqual(len(result["tests"]), len(expected["tests"]))
        for got, want in zip(result["tests"], expected["tests"]):
            self.assertEqual(got["test_id"], want["test_id"])
            self.assertEqual(got["passed"], want["passed"])
        # Downstream evidence path sees the same decisive failure.
        snapshot = pipe.default_learner_snapshot(problem)
        pack = pipe.build_pack_for_submission("x=1\n", problem, result, snapshot)
        self.assertEqual(pack.failed_test_id, expected["failed_test_id"])
        attempt = pipe.attempt_from_execution(problem, result)
        self.assertFalse(attempt.passed)

    def test_malformed_response_raises_bad_response(self):
        problem = bank_loader.load_problem(CANONICAL_ID)
        with self.assertRaises(execution_client.ExecutionServiceBadResponse):
            execution_client.validate_response({"status": "PASSED"}, problem=problem)
        bad = _passed_response(problem)
        bad["passed_count"] = 999  # inconsistent with tests
        with self.assertRaises(execution_client.ExecutionServiceBadResponse):
            execution_client.validate_response(bad, problem=problem)


class RemoteSubmissionTests(unittest.TestCase):
    def _production_client(self):
        # No runner_factory -> production HTTP path.
        from fastapi.testclient import TestClient

        return TestClient(create_app())

    def test_connection_failure_becomes_503(self):
        """D: execution-service unreachable -> HTTP 503, never a crash."""
        import httpx

        client = self._production_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]

        def boom(url, json=None, timeout=None):
            raise httpx.ConnectError("refused", request=None)

        with patch.object(execution_client.httpx, "post", side_effect=boom):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": CANONICAL_ID,
                    "code": "x = 1\n",
                },
            )
        self.assertEqual(resp.status_code, 503)

    def test_malformed_response_becomes_502_not_crash(self):
        client = self._production_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]

        def fake_post(url, json=None, timeout=None):
            return _FakeHttpResponse(200, {"bogus": True}, text='{"bogus": true}')

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": CANONICAL_ID,
                    "code": "x = 1\n",
                },
            )
        self.assertEqual(resp.status_code, 502)

    def test_execution_service_503_propagates_as_503(self):
        client = self._production_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]

        def fake_post(url, json=None, timeout=None):
            return _FakeHttpResponse(503, None, text="Docker unavailable")

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": CANONICAL_ID,
                    "code": "x = 1\n",
                },
            )
        self.assertEqual(resp.status_code, 503)

    def test_passed_submission_via_http_unlocks_transfer(self):
        problem = bank_loader.load_problem(CANONICAL_ID)
        client = self._production_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]

        def fake_post(url, json=None, timeout=None):
            return _FakeHttpResponse(200, _passed_response(problem))

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": CANONICAL_ID,
                    "code": "x = 1\n",
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "PASSED")
        self.assertTrue(body["transfer_available"])

    def test_no_docker_instantiation_on_production_path(self):
        """E: production submission never touches DockerSandboxRunner."""
        problem = bank_loader.load_problem(CANONICAL_ID)
        client = self._production_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]

        def fake_post(url, json=None, timeout=None):
            return _FakeHttpResponse(200, _passed_response(problem))

        # If the old Docker path were used, execution_modules() would be
        # consulted to build PythonRunner/DockerSandboxRunner. Fail the
        # test loudly if that happens on the production path.
        original_modules = pipe.execution_modules

        def guarded_modules():
            raise AssertionError(
                "production path must not load local execution modules/Docker"
            )

        with (
            patch.object(execution_client.httpx, "post", side_effect=fake_post),
            patch.object(pipe, "execution_modules", side_effect=guarded_modules),
        ):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": CANONICAL_ID,
                    "code": "x = 1\n",
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        # Keep reference so linters do not flag the import as unused.
        self.assertTrue(callable(original_modules))

    def test_default_factory_never_creates_docker_runner(self):
        """E: _default_runner_factory fails closed instead of using Docker."""
        with self.assertRaises(RuntimeError):
            student_mod._default_runner_factory("python", 5.0)
        with self.assertRaises(ValueError):
            student_mod._default_runner_factory("java", 5.0)
        source = Path(student_mod.__file__).read_text(encoding="utf-8")
        factory_src = source.split("def _default_runner_factory")[1].split(
            "\n# ---", 1
        )[0]
        self.assertNotIn("PythonRunner", factory_src)
        self.assertNotIn("execution_modules", factory_src)
        self.assertNotIn("DockerSandboxRunner(", factory_src)

    def test_injected_factory_still_bypasses_http(self):
        """F: explicit runner_factory (tests) never touches HTTP."""
        from fake_runner import make_client  # noqa: E402
        from fake_runner import WRONG_CODE  # noqa: E402

        client = make_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]

        def boom(url, json=None, timeout=None):  # pragma: no cover
            raise AssertionError("injected path must not use HTTP")

        with patch.object(execution_client.httpx, "post", side_effect=boom):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": CANONICAL_ID,
                    "code": WRONG_CODE,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["outcome"], "FAILED")

    def test_never_executes_locally_on_http_failure(self):
        """Core-backend must not fall back to local execution when HTTP fails."""
        import httpx

        marker = "print('PWNED')"
        client = self._production_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]

        def boom(url, json=None, timeout=None):
            raise httpx.ConnectError("down", request=None)

        with patch.object(execution_client.httpx, "post", side_effect=boom):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": CANONICAL_ID,
                    "code": marker,
                },
            )
        # Fail closed with 503; the payload must not appear as executed output.
        self.assertEqual(resp.status_code, 503)
        self.assertNotIn("PWNED", resp.text)


if __name__ == "__main__":
    unittest.main()
