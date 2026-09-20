"""Phase 24: hidden decisive-test values must not leak into student prose.

Regression tests for a genuine student-safety gap: when the decisive
failed test is hidden, the deterministic rule explanation
("(decisive H2: expected 6, got 5)") and the intervention action
("decisive test H2 (expected '6', observed '5')") exposed the hidden
test's expected/observed values, defeating the ``to_student_view``
redaction contract. The fix redacts those fixed template clauses in the
student view layer (presentation only — diagnosis, confidence, evidence
refs, and learner recording are unchanged).

Covers:
- unit: public-decisive text is byte-identical (no behavior change);
- unit: hidden M01 / M05 / intervention clauses redacted, meaning kept;
- unit: non-string / missing values pass through safely;
- e2e: a submission failing ONLY a hidden test still diagnoses C3-M01
  (engine value preserved) with no hidden values in student prose.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
_SERVICE_DIR = _ROOT / "services" / "core-backend"
for _p in (str(_ROOT), str(_SERVICE_DIR), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fake_runner import CANONICAL_ID, make_client  # noqa: E402

from app import student as student_mod  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from packages.problem_bank import loader as bank_loader  # noqa: E402

M01_EXPLANATION = (
    "the code iterates range(len(nums) - 1), excluding the terminal index, "
    "and every failed test undercounts by exactly one "
    "(decisive H2: expected 6, got 5). This matches C3-M01 off-by-one-bounds."
)
M05_EXPLANATION = (
    "the code iterates range(1, n) with an unadjusted stop, and every "
    "failed test drops exactly its terminal value "
    "(decisive H1: n=1, expected 0, got -1). This matches C3-M05."
)
ACTION = (
    "Trace the loop on decisive test H2 (expected '6', observed '5'): "
    "write down the last index the loop visits, then re-run the tests."
)

HIDDEN_KWARGS = {
    "test_id": "H2",
    "expected": "6",
    "actual": "5",
}


class RedactorUnitTests(unittest.TestCase):
    def test_public_decisive_is_untouched(self):
        self.assertEqual(
            student_mod._redact_hidden_decisive_values(
                M01_EXPLANATION, test_id="P2", expected="3", actual="2"
            ),
            M01_EXPLANATION,
        )
        # Empty redaction args (public decisive) leave views byte-identical.
        pack = SimpleNamespace(failed_test_id="P2", failed_tests=[])
        problem = bank_loader.load_problem(CANONICAL_ID)
        self.assertEqual(student_mod._hidden_redaction_args(problem, pack), {})

    def test_hidden_m01_clause_redacted_meaning_kept(self):
        out = student_mod._redact_hidden_decisive_values(
            M01_EXPLANATION, **HIDDEN_KWARGS
        )
        self.assertIn("undercounts by exactly one", out)
        self.assertIn("hidden test", out)
        self.assertNotIn("expected 6", out)
        self.assertNotIn("got 5", out)

    def test_hidden_m05_clause_redacted(self):
        out = student_mod._redact_hidden_decisive_values(
            M05_EXPLANATION,
            test_id="H1",
            expected="0",
            actual="-1",
        )
        self.assertIn("hidden test", out)
        self.assertNotIn("expected 0", out)

    def test_hidden_intervention_action_redacted(self):
        out = student_mod._redact_hidden_decisive_values(ACTION, **HIDDEN_KWARGS)
        self.assertIn("hidden test", out)
        self.assertNotIn("'6'", out)
        self.assertNotIn("'5'", out)

    def test_passthrough_on_missing_values(self):
        self.assertIsNone(
            student_mod._redact_hidden_decisive_values(
                None, test_id="H2", expected="6", actual="5"
            )
        )
        self.assertEqual(
            student_mod._redact_hidden_decisive_values(
                M01_EXPLANATION, test_id="H2", expected=None, actual="5"
            ),
            M01_EXPLANATION,
        )
        self.assertEqual(
            student_mod._redact_hidden_decisive_values(
                M01_EXPLANATION, test_id=None, expected="6", actual="5"
            ),
            M01_EXPLANATION,
        )


class HiddenDecisiveEndToEndTests(unittest.TestCase):
    """Fail ONLY hidden test H2: rule still fires, values stay hidden."""

    @staticmethod
    def _client() -> TestClient:
        canonical = bank_loader.load_problem(CANONICAL_ID)
        expected_by_input = {
            c.input: c.expected_output for c in canonical.all_tests()
        }
        h2_input = next(
            c.input for c in canonical.hidden_tests if c.id == "H2"
        )

        class HiddenOnlyRunner:
            language = "python"

            def compile(self, code: str, timeout_seconds: float) -> None:
                return None

            def run_single(self, code: str, stdin_data: str, timeout_seconds: float):
                if stdin_data == h2_input:
                    return SimpleNamespace(
                        stdout="5\n", stderr="", exit_code=0,
                        timed_out=False, time_ms=5,
                    )
                return SimpleNamespace(
                    stdout=expected_by_input[stdin_data] + "\n", stderr="",
                    exit_code=0, timed_out=False, time_ms=5,
                )

        return TestClient(
            create_app(runner_factory=lambda lang, timeout: HiddenOnlyRunner())
        )

    def test_hidden_decisive_diagnoses_without_leaking_values(self):
        client = self._client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]
        code = (
            "def count_divisible(nums, k):\n"
            "    count = 0\n"
            "    for i in range(len(nums) - 1):\n"
            "        if nums[i] % k == 0:\n"
            "            count += 1\n"
            "    return count\n"
        )
        body = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": code},
        ).json()
        self.assertEqual(body["outcome"], "FAILED")
        self.assertEqual(body["execution"]["failed_test_id"], "H2")
        # Engine value preserved: the rule still fires on hidden evidence.
        diagnosis = body["diagnosis"]
        self.assertIsNotNone(diagnosis)
        assert diagnosis is not None
        self.assertEqual(diagnosis["misconception_id"], "C3-M01")
        # ... but hidden values never reach student prose.
        self.assertNotIn("expected 6", diagnosis["explanation"])
        self.assertNotIn("got 5", diagnosis["explanation"])
        self.assertIn("hidden test", diagnosis["explanation"])
        action = body["intervention"]["recommended_action"]
        self.assertNotIn("'6'", action)
        self.assertNotIn("'5'", action)
        self.assertIn("hidden test", action)
        # Execution redaction still intact.
        self.assertIsNone(body["execution"]["expected_output"])
        for entry in body["execution"]["tests"]:
            if entry.get("test_id") == "H2":
                self.assertTrue(entry.get("is_hidden"))
                self.assertIsNone(entry["expected_output"])

    def test_public_decisive_keeps_values(self):
        # Control: the normal public-decisive path still shows its values
        # (existing behavior pinned, not redacted away).
        client = make_client()
        session_id = client.post("/student/sessions", json={}).json()["session_id"]
        body = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": CANONICAL_ID,
                "code": (
                    "RANGE_BUG\n"
                    "def count_divisible(nums, k):\n"
                    "    count = 0\n"
                    "    for i in range(len(nums) - 1):\n"
                    "        if nums[i] % k == 0:\n"
                    "            count += 1\n"
                    "    return count\n"
                ),
            },
        ).json()
        self.assertEqual(body["execution"]["failed_test_id"], "P2")
        self.assertIn("expected 3, got 2", body["diagnosis"]["explanation"])


if __name__ == "__main__":
    unittest.main()
