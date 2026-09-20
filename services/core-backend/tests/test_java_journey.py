"""Step 21B-21D: Java student journey + language isolation (core-backend).

Covers the task checklist through the existing orchestration only
(injected marker runner, no Docker; HTTP path via mocked httpx):

- Python session creation still works.
- Java session creation works.
- Unsupported language rejected.
- Java session receives Java problem.
- Python session never receives Java problem.
- Java session never receives Python problem.
- Java code reaches execution-service (HTTP payload language == java).
- Java wrong submission -> normal FAILED result + generic diagnosis.
- Java retry can pass -> transfer unlocked (Java transfer, not Python).
- Java transfer can pass -> VERIFIED_IMPROVED.
- Java attempts update Java learner state (isolated per journey).
- Java adaptive recommendation remains Java-only.
- Cross-language verification rejected.
- Java diagnosis stays on generic/fallback path (no Java rule prefix).

Run from repo root:
    python -m unittest services.core-backend.tests.test_java_journey -v
NOTE: hyphen dir; use discover: python -m unittest discover -s services/core-backend/tests -t . -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
_SERVICE_DIR = _ROOT / "services" / "core-backend"
for _p in (str(_ROOT), str(_SERVICE_DIR), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fake_runner import (  # noqa: E402
    CANONICAL_ID as PY_CANONICAL,
    FIXED_CODE as PY_FIXED,
    TRANSFER_CODE as PY_TRANSFER_CODE,
    TRANSFER_ID as PY_TRANSFER,
    WRONG_CODE as PY_WRONG,
    MarkerRunner as PyMarkerRunner,
    make_client as make_py_client,
)
from fastapi.testclient import TestClient  # noqa: E402

from app import execution_client  # noqa: E402
from app.main import create_app  # noqa: E402
from packages.adaptive import (  # noqa: E402
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    ProblemInfo,
    recommend_next_actions,
)
from packages.problem_bank import loader as bank_loader  # noqa: E402
from packages.verification import (  # noqa: E402
    VerificationAttempt,
    VerificationContext,
    verify_improvement,
)

JAVA_CANONICAL = "JAVA-C3-COUNT-DIV"
JAVA_TRANSFER = "JAVA-C3-COUNT-DIV-TRANSFER"

JAVA_WRONG_CODE = (
    "JAVA_BUG\n"
    "public class Main {\n"
    "    public static int countDivisible(int[] nums, int k) {\n"
    "        int count = 0;\n"
    "        for (int i = 0; i < nums.length - 1; i++) {\n"
    "            if (nums[i] % k == 0) count += 1;\n"
    "        }\n"
    "        return count;\n"
    "    }\n"
    "    public static void main(String[] args) throws Exception {}\n"
    "}\n"
)

JAVA_FIXED_CODE = (
    "public class Main {\n"
    "    public static int countDivisible(int[] nums, int k) {\n"
    "        int count = 0;\n"
    "        for (int x : nums) { if (x % k == 0) count += 1; }\n"
    "        return count;\n"
    "    }\n"
    "    public static void main(String[] args) throws Exception {\n"
    "        java.util.Scanner sc = new java.util.Scanner(System.in);\n"
    "        int n = sc.nextInt(); int k = sc.nextInt();\n"
    "        int[] nums = new int[n];\n"
    "        for (int i = 0; i < n && sc.hasNextInt(); i++) nums[i] = sc.nextInt();\n"
    "        System.out.println(countDivisible(nums, k));\n"
    "    }\n"
    "}\n"
)

JAVA_TRANSFER_CODE = (
    "public class Main {\n"
    "    public static int countColdDays(int[] temps, int threshold) {\n"
    "        int count = 0;\n"
    "        for (int t : temps) { if (t < threshold) count += 1; }\n"
    "        return count;\n"
    "    }\n"
    "    public static void main(String[] args) throws Exception {\n"
    "        java.util.Scanner sc = new java.util.Scanner(System.in);\n"
    "        int n = sc.nextInt(); int threshold = sc.nextInt();\n"
    "        int[] temps = new int[n];\n"
    "        for (int i = 0; i < n && sc.hasNextInt(); i++) temps[i] = sc.nextInt();\n"
    "        System.out.println(countColdDays(temps, threshold));\n"
    "    }\n"
    "}\n"
)


class JavaMarkerRunner:
    """Fake Java runner (never executes student code)."""

    language = "java"

    def __init__(self) -> None:
        canonical = bank_loader.load_problem_all(JAVA_CANONICAL)
        transfer = bank_loader.load_problem_all(JAVA_TRANSFER)
        self._canonical = {c.input: c.expected_output for c in canonical.all_tests()}
        self._transfer = {c.input: c.expected_output for c in transfer.all_tests()}

    def compile(self, code: str, timeout_seconds: float) -> None:
        return None

    def run_single(self, code: str, stdin_data: str, timeout_seconds: float):
        if "HANG" in code:
            return SimpleNamespace(
                stdout="", stderr="", exit_code=0, timed_out=True, time_ms=5000
            )
        if "CRASH" in code:
            return SimpleNamespace(
                stdout="",
                stderr="Exception in thread main java.lang.ArithmeticException\n",
                exit_code=1,
                timed_out=False,
                time_ms=5,
            )
        if "JAVA_BUG" in code and stdin_data in self._canonical:
            return SimpleNamespace(
                stdout="9999\n", stderr="", exit_code=0, timed_out=False, time_ms=5
            )
        if "TRANSFER_BUG" in code and stdin_data in self._transfer:
            return SimpleNamespace(
                stdout="9999\n", stderr="", exit_code=0, timed_out=False, time_ms=5
            )
        expected = self._canonical.get(stdin_data, self._transfer.get(stdin_data))
        return SimpleNamespace(
            stdout=expected + "\n", stderr="", exit_code=0, timed_out=False, time_ms=5
        )


def make_dual_client() -> TestClient:
    """TestClient whose runner factory supports both python and java."""

    def factory(lang: str, timeout: float):
        if str(lang).strip().lower() == "java":
            return JavaMarkerRunner()
        return PyMarkerRunner()

    return TestClient(create_app(runner_factory=factory))


def _new_session(client: TestClient, track: str | None = None) -> dict:
    payload: dict = {} if track is None else {"language_track": track}
    resp = client.post("/student/sessions", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


class SessionCreationTests(unittest.TestCase):
    def test_python_session_still_works_default(self):
        body = _new_session(make_dual_client())
        self.assertEqual(body["language_track"], "python")
        self.assertEqual(body["problem"]["problem_id"], PY_CANONICAL)
        self.assertEqual(body["problem"]["language"], "python")

    def test_python_session_explicit(self):
        body = _new_session(make_dual_client(), "python")
        self.assertEqual(body["language_track"], "python")
        self.assertEqual(body["problem"]["problem_id"], PY_CANONICAL)

    def test_java_session_creation(self):
        body = _new_session(make_dual_client(), "java")
        self.assertEqual(body["language_track"], "java")
        self.assertEqual(body["problem"]["problem_id"], JAVA_CANONICAL)
        self.assertEqual(body["problem"]["language"], "java")
        self.assertIn("public class Main", body["problem"]["starter_code"])

    def test_unsupported_language_rejected(self):
        client = make_dual_client()
        for bad in ("cobol", "ruby", "", "  "):
            resp = client.post("/student/sessions", json={"language_track": bad})
            # Empty string falls back to python default; others must 422.
            if bad.strip() == "":
                self.assertEqual(resp.status_code, 200, resp.text)
            else:
                self.assertEqual(resp.status_code, 422, resp.text)

    def test_java_session_receives_java_problem(self):
        client = make_dual_client()
        session_id = _new_session(client, "java")["session_id"]
        resp = client.get(
            f"/student/problems/{JAVA_CANONICAL}", params={"session_id": session_id}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["language"], "java")

    def test_python_session_never_receives_java_problem(self):
        client = make_dual_client()
        session_id = _new_session(client, "python")["session_id"]
        resp = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_TRANSFER,
                "code": JAVA_TRANSFER_CODE,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_java_session_never_receives_python_problem(self):
        client = make_dual_client()
        session_id = _new_session(client, "java")["session_id"]
        resp = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": PY_CANONICAL,
                "code": PY_FIXED,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_problem_catalog_is_language_filtered(self):
        client = make_dual_client()
        py_id = _new_session(client, "python")["session_id"]
        py_catalog = client.get("/student/problems", params={"session_id": py_id}).json()
        self.assertEqual(py_catalog["language_track"], "python")
        self.assertGreater(len(py_catalog["problems"]), 0)
        for entry in py_catalog["problems"]:
            self.assertEqual(entry["language"], "python")
        self.assertNotIn(
            JAVA_CANONICAL, [p["problem_id"] for p in py_catalog["problems"]]
        )
        java_id = _new_session(client, "java")["session_id"]
        java_catalog = client.get(
            "/student/problems", params={"session_id": java_id}
        ).json()
        self.assertEqual(java_catalog["language_track"], "java")
        self.assertGreater(len(java_catalog["problems"]), 0)
        for entry in java_catalog["problems"]:
            self.assertEqual(entry["language"], "java")
        self.assertNotIn(
            PY_CANONICAL, [p["problem_id"] for p in java_catalog["problems"]]
        )


class JavaJourneyTests(unittest.TestCase):
    def _java_client_session(self) -> tuple[TestClient, str]:
        client = make_dual_client()
        session_id = _new_session(client, "java")["session_id"]
        return client, session_id

    def test_java_wrong_submission_produces_normal_failure(self):
        client, session_id = self._java_client_session()
        resp = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_WRONG_CODE,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "FAILED")
        self.assertEqual(body["problem_id"], JAVA_CANONICAL)
        self.assertEqual(body["variant_role"], "canonical")
        self.assertFalse(body["transfer_available"])
        self.assertIsNone(body["verification"])
        # Execution shape mirrors the python C3 failure contract.
        execution = body["execution"]
        self.assertEqual(execution["failed_count"] > 0, True)
        self.assertIsNotNone(execution["failed_test_id"])

    def test_java_diagnosis_uses_generic_fallback_path(self):
        client, session_id = self._java_client_session()
        body = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_WRONG_CODE,
            },
        ).json()
        diagnosis = body["diagnosis"]
        self.assertIsNotNone(diagnosis)
        assert diagnosis is not None
        # Java bank candidates are C3-M01/C3-M04; fallback picks deterministically.
        self.assertIn(diagnosis["misconception_id"], ("C3-M01", "C3-M04"))
        self.assertEqual(diagnosis["source"], "fallback")
        self.assertTrue(diagnosis["explanation"].strip())
        # No Java-specific deterministic rule prefix leaks into student text.
        self.assertNotIn("Rule ", diagnosis["explanation"])
        self.assertIn(
            diagnosis["confidence_label"], ("likely", "possible", "uncertain")
        )

    def test_java_retry_can_pass_and_unlocks_java_transfer(self):
        client, session_id = self._java_client_session()
        client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_WRONG_CODE,
            },
        )
        resp = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_FIXED_CODE,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "PASSED")
        self.assertTrue(body["transfer_available"])
        transfer = body["transfer_problem"]
        self.assertIsNotNone(transfer)
        assert transfer is not None
        # Must be the Java transfer, never the Python one.
        self.assertEqual(transfer["problem_id"], JAVA_TRANSFER)
        self.assertNotEqual(transfer["problem_id"], PY_TRANSFER)
        self.assertEqual(transfer["language"], "java")

    def test_java_transfer_can_pass_and_verifies_improvement(self):
        client, session_id = self._java_client_session()
        client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_WRONG_CODE,
            },
        )
        client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_FIXED_CODE,
            },
        )
        resp = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_TRANSFER,
                "code": JAVA_TRANSFER_CODE,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "PASSED")
        self.assertIsNotNone(body["verification"])
        assert body["verification"] is not None
        self.assertEqual(body["verification"]["outcome"], "VERIFIED_IMPROVED")
        self.assertEqual(body["journey_state"]["stage"], "transfer_done")

    def test_java_attempts_update_learner_state_isolated(self):
        client, session_id = self._java_client_session()
        client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_WRONG_CODE,
            },
        )
        concepts = client.get(
            "/student/concepts", params={"session_id": session_id}
        ).json()
        by_id = {c["concept_id"]: c for c in concepts["concepts"]}
        c3 = by_id["C3"]
        self.assertEqual(c3["status"], "started")
        self.assertEqual(c3["attempt_count"], 1)
        self.assertEqual(c3["fail_count"], 1)
        # Full journey: transfer pass records transfer stats on the same track.
        client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_FIXED_CODE,
            },
        )
        client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_TRANSFER,
                "code": JAVA_TRANSFER_CODE,
            },
        )
        history = client.get(
            "/student/history", params={"session_id": session_id}
        ).json()
        self.assertGreaterEqual(history["total"], 2)
        for item in history["items"]:
            self.assertIn(item["problem_id"], (JAVA_CANONICAL, JAVA_TRANSFER))
            self.assertNotIn(item["problem_id"], (PY_CANONICAL, PY_TRANSFER))

    def test_python_state_remains_isolated_from_java(self):
        client = make_dual_client()
        py_id = _new_session(client, "python")["session_id"]
        java_id = _new_session(client, "java")["session_id"]
        client.post(
            "/student/submissions",
            json={
                "session_id": java_id,
                "problem_id": JAVA_CANONICAL,
                "code": JAVA_WRONG_CODE,
            },
        )
        untouched = client.get(
            "/student/concepts", params={"session_id": py_id}
        ).json()
        by_id = {c["concept_id"]: c for c in untouched["concepts"]}
        self.assertEqual(by_id["C3"]["status"], "not_started")
        self.assertEqual(by_id["C3"]["attempt_count"], 0)

    def test_transfer_before_canonical_pass_rejected_java(self):
        client, session_id = self._java_client_session()
        resp = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": JAVA_TRANSFER,
                "code": JAVA_TRANSFER_CODE,
            },
        )
        self.assertEqual(resp.status_code, 409)


class JavaExecutionServiceTests(unittest.TestCase):
    def _passed_response(self, problem, time_ms: int = 5) -> dict:
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

    def _failed_response(self, problem, fail_index: int = 0) -> dict:
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

    def test_java_code_reaches_execution_service_via_http(self):
        from fastapi.testclient import TestClient as _TC

        problem = bank_loader.load_problem_all(JAVA_CANONICAL)
        client = _TC(create_app())  # production HTTP path
        session_id = client.post(
            "/student/sessions", json={"language_track": "java"}
        ).json()["session_id"]
        captured: dict = {}

        class _Resp:
            def __init__(self, payload):
                self.status_code = 200
                self._payload = payload
                self.text = ""

            def json(self):
                return self._payload

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return _Resp(self._failed_response(problem))

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": JAVA_CANONICAL,
                    "code": JAVA_WRONG_CODE,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(captured["url"].endswith("/execute"))
        self.assertEqual(captured["json"]["language"], "java")
        self.assertEqual(resp.json()["outcome"], "FAILED")
        # Error payloads use the existing ExecutionResult model shape.
        self.assertIn(resp.json()["execution"]["status"], ("FAILED",))

    def test_java_retry_pass_via_http_unlocks_transfer(self):
        from fastapi.testclient import TestClient as _TC

        problem = bank_loader.load_problem_all(JAVA_CANONICAL)
        client = _TC(create_app())
        session_id = client.post(
            "/student/sessions", json={"language_track": "java"}
        ).json()["session_id"]

        class _Resp:
            def __init__(self, payload):
                self.status_code = 200
                self._payload = payload
                self.text = ""

            def json(self):
                return self._payload

        def fake_post(url, json=None, timeout=None):
            return _Resp(self._passed_response(problem))

        with patch.object(execution_client.httpx, "post", side_effect=fake_post):
            resp = client.post(
                "/student/submissions",
                json={
                    "session_id": session_id,
                    "problem_id": JAVA_CANONICAL,
                    "code": JAVA_FIXED_CODE,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "PASSED")
        self.assertEqual(body["transfer_problem"]["problem_id"], JAVA_TRANSFER)


class AdaptiveIsolationTests(unittest.TestCase):
    def _java_state(self, mastery=0.70, attempts=6):
        return ConceptState(
            concept_id="C3",
            mastery=mastery,
            mastery_band="proficient",
            trend="stable",
            attempt_count=attempts,
            hint_dependence=0.0,
            transfer_success_rate=0.0,
            language_track="java",
        )

    def _py_state(self, mastery=0.70, attempts=6):
        return ConceptState(
            concept_id="C3",
            mastery=mastery,
            mastery_band="proficient",
            trend="stable",
            attempt_count=attempts,
            hint_dependence=0.0,
            transfer_success_rate=0.0,
            language_track="python",
        )

    def test_problem_info_language_field(self):
        tagged = ProblemInfo(
            problem_id="JAVA-C3-COUNT-DIV",
            concept_id="C3",
            difficulty=2,
            isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
            variant_role="canonical",
            language="java",
        )
        self.assertEqual(tagged.language, "java")
        self.assertEqual(tagged.to_dict()["language"], "java")
        self.assertEqual(ProblemInfo.from_dict(tagged.to_dict()), tagged)
        # Backward compat: untagged entries carry no language key.
        legacy = ProblemInfo(
            problem_id="PY-C3-COUNT-DIV",
            concept_id="C3",
            difficulty=2,
            isomorphic_group_id="ISO-C3-COUNT-DIV",
            variant_role="canonical",
        )
        self.assertIsNone(legacy.language)
        self.assertNotIn("language", legacy.to_dict())
        self.assertEqual(ProblemInfo.from_dict(legacy.to_dict()), legacy)

    def test_java_recommendation_remains_java_only(self):
        probs = [
            ProblemInfo(
                problem_id="PY-C3-COUNT-DIV",
                concept_id="C3",
                difficulty=2,
                isomorphic_group_id="ISO-C3-COUNT-DIV",
                variant_role="canonical",
                language="python",
            ),
            ProblemInfo(
                problem_id="JAVA-C3-COUNT-DIV",
                concept_id="C3",
                difficulty=2,
                isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
                variant_role="canonical",
                language="java",
            ),
            ProblemInfo(
                problem_id="JAVA-C3-COUNT-DIV-TRANSFER",
                concept_id="C3",
                difficulty=2,
                isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
                variant_role="transfer",
                language="java",
            ),
        ]
        recs = recommend_next_actions(
            [self._java_state()],
            [],
            [CurriculumInfo.from_taxonomy("C3")],
            probs,
            language_track="java",
        )
        self.assertGreater(len(recs), 0)
        for rec in recs:
            if rec.problem_id is not None:
                self.assertTrue(rec.problem_id.startswith("JAVA-"))

    def test_python_recommendation_never_returns_java(self):
        probs = [
            ProblemInfo(
                problem_id="PY-C3-COUNT-DIV",
                concept_id="C3",
                difficulty=2,
                isomorphic_group_id="ISO-C3-COUNT-DIV",
                variant_role="canonical",
                language="python",
            ),
            ProblemInfo(
                problem_id="JAVA-C3-COUNT-DIV",
                concept_id="C3",
                difficulty=2,
                isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
                variant_role="canonical",
                language="java",
            ),
        ]
        recs = recommend_next_actions(
            [self._py_state(mastery=0.45, attempts=5)],
            [],
            [CurriculumInfo.from_taxonomy("C3")],
            probs,
            language_track="python",
        )
        self.assertGreater(len(recs), 0)
        for rec in recs:
            if rec.problem_id is not None:
                self.assertFalse(rec.problem_id.startswith("JAVA-"))

    def test_cross_track_state_rejected(self):
        probs = [
            ProblemInfo(
                problem_id="PY-C3-COUNT-DIV",
                concept_id="C3",
                difficulty=2,
                isomorphic_group_id="ISO-C3-COUNT-DIV",
                variant_role="canonical",
                language="python",
            ),
        ]
        with self.assertRaises(ValueError):
            recommend_next_actions(
                [self._java_state()],
                [],
                [CurriculumInfo.from_taxonomy("C3")],
                probs,
                language_track="python",
            )


class VerificationIsolationTests(unittest.TestCase):
    def test_cross_language_verification_rejected(self):
        original = VerificationAttempt(
            problem_id=JAVA_CANONICAL,
            concept_id="C3",
            language_track="java",
            outcome="PASS",
            isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
        )
        transfer = VerificationAttempt(
            problem_id="PY-C3-COUNT-DIV-TRANSFER",
            concept_id="C3",
            language_track="python",
            outcome="PASS",
            is_transfer=True,
            isomorphic_group_id="ISO-C3-COUNT-DIV",
        )
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=JAVA_CANONICAL,
                transfer_problem_id="PY-C3-COUNT-DIV-TRANSFER",
                concept_id="C3",
                language_track="java",
                original_retry=original,
                transfer=transfer,
                isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
            )

    def test_java_canonical_plus_transfer_verifies(self):
        original = VerificationAttempt(
            problem_id=JAVA_CANONICAL,
            concept_id="C3",
            language_track="java",
            outcome="PASS",
            isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
        )
        transfer = VerificationAttempt(
            problem_id=JAVA_TRANSFER,
            concept_id="C3",
            language_track="java",
            outcome="PASS",
            is_transfer=True,
            isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
        )
        ctx = VerificationContext(
            original_problem_id=JAVA_CANONICAL,
            transfer_problem_id=JAVA_TRANSFER,
            concept_id="C3",
            language_track="java",
            original_retry=original,
            transfer=transfer,
            isomorphic_group_id="ISO-C3-COUNT-DIV-JAVA",
        )
        result = verify_improvement(ctx)
        self.assertEqual(result.outcome.value, "VERIFIED_IMPROVED")
        # Verification never computes mastery directly.
        self.assertFalse(hasattr(result, "mastery"))


if __name__ == "__main__":
    unittest.main()
