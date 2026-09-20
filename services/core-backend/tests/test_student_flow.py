"""Unit tests for Step 16: Student-Facing API vertical slice (core-backend).

Covers the minimum student flow through the existing intelligence
(orchestrated, never reimplemented):

    POST /student/sessions -> canonical problem
    POST /student/submissions (canonical, fails)
      -> execution + diagnosis + intervention + recommendations
    POST /student/submissions (canonical retry, passes)
      -> transfer unlocked (no isomorphic reveal)
    POST /student/submissions (transfer)
      -> execution + verification + learner update + recommendations
    GET /student/journey -> stage / verification / next recommendation

Execution uses a marker-dispatched fake runner (no Docker, no host
execution of student code): code containing ``RANGE_BUG`` reproduces the
Step 14 off-by-one via an INDEPENDENT reimplementation; ``TRANSFER_BUG``
fails transfer; ``CRASH``/``HANG`` markers produce runtime/timeout
outcomes; anything else passes honestly against the bank's own tests.

Run from repo root:
    python -m unittest discover -s services/core-backend/tests -t . -v

NOTE: ``services/core-backend`` is not importable (hyphen), so this file
bootstraps sys.path with the repo root AND the service dir.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
_SERVICE_DIR = _ROOT / "services" / "core-backend"
for _p in (str(_ROOT), str(_SERVICE_DIR), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fake_runner import (  # noqa: E402
    CANONICAL_ID,
    FIXED_CODE,
    TRANSFER_CODE,
    TRANSFER_ID,
    WRONG_CODE,
    make_client,
)
from fastapi.testclient import TestClient  # noqa: E402

from packages.problem_bank import loader as bank_loader  # noqa: E402

_APP_DIR = _SERVICE_DIR / "app"


def _client() -> TestClient:
    return make_client()


def _new_session(client: TestClient) -> dict:
    resp = client.post("/student/sessions", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


class StudentSessionTests(unittest.TestCase):
    def test_health_still_ok(self):
        body = _client().get("/health").json()
        self.assertEqual(body, {"status": "ok", "service": "core-backend"})

    def test_session_returns_safe_canonical_problem(self):
        body = _new_session(_client())
        self.assertTrue(body["session_id"].strip())
        self.assertEqual(body["language_track"], "python")
        problem = body["problem"]
        for key in (
            "problem_id", "language", "concept_id", "title", "statement",
            "constraints", "input_format", "output_format", "starter_code",
            "difficulty",
        ):
            self.assertIn(key, problem)
        self.assertEqual(problem["problem_id"], CANONICAL_ID)
        self.assertEqual(problem["language"], "python")
        self.assertEqual(problem["concept_id"], "C3")
        # No tests (and no answers) in the problem response.
        self.assertNotIn("public_tests", problem)
        self.assertNotIn("hidden_tests", problem)
        self.assertNotIn("expected_output", str(problem))

    def test_problem_endpoint_returns_safe_metadata(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        resp = client.get(
            f"/student/problems/{CANONICAL_ID}", params={"session_id": session_id}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["problem_id"], CANONICAL_ID)
        self.assertNotIn("expected_output", resp.text)

    def test_hidden_expected_outputs_never_returned(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        resp = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        hidden_answers = [t.expected_output for t in transfer.hidden_tests]
        canonical = bank_loader.load_problem(CANONICAL_ID)
        hidden_answers += [t.expected_output for t in canonical.hidden_tests]
        for answer in hidden_answers:
            self.assertNotIn(f'"expected_output": "{answer}"', resp.text)

    def test_invalid_problem_id_rejected(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        resp = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": "NO-SUCH-PROBLEM", "code": "x=1\n"},
        )
        self.assertIn(resp.status_code, (404, 422))

    def test_unknown_session_rejected(self):
        client = _client()
        resp = client.post(
            "/student/submissions",
            json={"session_id": "nope", "problem_id": CANONICAL_ID, "code": "x=1\n"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_language_mismatch_rejected(self):
        client = _client()
        resp = client.post("/student/sessions", json={"language_track": "java"})
        self.assertEqual(resp.status_code, 422)
        resp2 = client.post("/student/sessions", json={"language_track": "cobol"})
        self.assertEqual(resp2.status_code, 422)

    def test_empty_code_rejected(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        resp = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": "   \n"},
        )
        self.assertEqual(resp.status_code, 422)


class SubmissionFlowTests(unittest.TestCase):
    def test_failed_submission_returns_safe_failure(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        resp = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "FAILED")
        execution = body["execution"]
        self.assertEqual(
            (execution["passed_count"], execution["failed_count"]), (2, 3)
        )
        self.assertEqual(execution["failed_test_id"], "P2")
        self.assertFalse(body["transfer_available"])
        self.assertIsNone(body["transfer_problem"])
        self.assertIsNone(body["verification"])
        # Safe per-test view: hidden expectations redacted.
        for entry in execution["tests"]:
            if entry.get("is_hidden"):
                self.assertIsNone(entry["expected_output"])

    def test_diagnosis_returned_when_available(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        body = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        ).json()
        diagnosis = body["diagnosis"]
        self.assertIsNotNone(diagnosis)
        assert diagnosis is not None
        self.assertEqual(diagnosis["misconception_id"], "C3-M01")
        self.assertTrue(diagnosis["explanation"].strip())
        self.assertNotIn("Rule ", diagnosis["explanation"])
        self.assertIn(diagnosis["confidence_label"], ("likely", "possible", "uncertain"))
        self.assertEqual(diagnosis["evidence_summary"]["failed_test_id"], "P2")
        self.assertIn(diagnosis["source"], ("llm", "fallback"))

    def test_intervention_returned_when_available(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        body = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        ).json()
        intervention = body["intervention"]
        self.assertIsNotNone(intervention)
        assert intervention is not None
        self.assertEqual(
            set(intervention),
            {
                "misconception_id", "intervention_level", "intervention_type",
                "target_skill", "explanation", "recommended_action",
                "student_message",
            },
        )
        self.assertEqual(intervention["misconception_id"], "C3-M01")
        self.assertEqual(intervention["intervention_type"], "BOUNDARY_CHECK")
        self.assertEqual(intervention["intervention_level"], "L1")
        self.assertTrue(intervention["student_message"].strip())
        self.assertTrue(intervention["recommended_action"].strip())

    def test_recommendations_come_from_adaptive_engine(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        body = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        ).json()
        recs = body["recommendations"]
        self.assertGreater(len(recs), 0)
        for rec in recs:
            self.assertEqual(
                set(rec), {"action", "reason", "problem_id", "problem_title"}
            )
            self.assertTrue(rec["action"].strip())
            self.assertTrue(rec["reason"].strip())

    def test_retry_reaches_execution_and_can_still_fail(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        payload = {"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE}
        first = client.post("/student/submissions", json=payload).json()
        second = client.post("/student/submissions", json=payload).json()
        self.assertEqual(second["outcome"], "FAILED")
        self.assertIsNotNone(second["diagnosis"])
        self.assertFalse(second["transfer_available"])
        self.assertEqual(
            second["execution"]["failed_count"], first["execution"]["failed_count"]
        )

    def test_successful_retry_enables_transfer_without_reveal(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        resp = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": FIXED_CODE},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "PASSED")
        self.assertTrue(body["transfer_available"])
        self.assertIsNone(body["diagnosis"])
        transfer = body["transfer_problem"]
        self.assertIsNotNone(transfer)
        assert transfer is not None
        self.assertEqual(transfer["problem_id"], TRANSFER_ID)
        # The isomorphic relationship is never revealed student-side.
        self.assertNotIn("isomorphic", resp.text.lower())
        self.assertNotIn("ISO-C3", resp.text)

    def test_transfer_unavailable_before_canonical_pass(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        resp = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": TRANSFER_ID, "code": TRANSFER_CODE},
        )
        self.assertEqual(resp.status_code, 409)

    def test_transfer_submission_verifies_improvement(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": FIXED_CODE},
        )
        resp = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": TRANSFER_ID, "code": TRANSFER_CODE},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["outcome"], "PASSED")
        verification = body["verification"]
        self.assertIsNotNone(verification)
        assert verification is not None
        self.assertEqual(verification["outcome"], "VERIFIED_IMPROVED")
        self.assertTrue(verification["message"].strip())
        self.assertGreater(len(body["recommendations"]), 0)
        state = body["journey_state"]
        self.assertEqual(state["stage"], "transfer_done")
        self.assertFalse(state["mastery_claim"])

    def test_failed_transfer_preserves_surface_fix_semantics(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": FIXED_CODE},
        )
        body = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": TRANSFER_ID,
                "code": "TRANSFER_BUG\n" + TRANSFER_CODE,
            },
        ).json()
        self.assertEqual(body["outcome"], "FAILED")
        self.assertEqual(body["verification"]["outcome"], "SURFACE_FIX")
        self.assertTrue(body["transfer_available"])

    def test_journey_endpoint_reports_progress(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        start = client.get("/student/journey", params={"session_id": session_id}).json()
        self.assertEqual(start["journey_state"]["stage"], "started")
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        mid = client.get("/student/journey", params={"session_id": session_id}).json()
        self.assertEqual(mid["journey_state"]["stage"], "practicing")
        self.assertIsNone(mid["verification"])
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": FIXED_CODE},
        )
        client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": TRANSFER_ID, "code": TRANSFER_CODE},
        )
        end = client.get("/student/journey", params={"session_id": session_id}).json()
        self.assertEqual(end["journey_state"]["stage"], "transfer_done")
        self.assertEqual(end["verification"]["outcome"], "VERIFIED_IMPROVED")
        self.assertGreater(len(end["recommendations"]), 0)

    def test_runtime_error_and_timeout_are_safe(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        crash = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": "CRASH\nx = 1\n"},
        ).json()
        self.assertEqual(crash["outcome"], "RUNTIME_ERROR")
        self.assertIsNone(crash["diagnosis"])
        self.assertIsNone(crash["intervention"])
        hang = client.post(
            "/student/submissions",
            json={"session_id": session_id, "problem_id": CANONICAL_ID, "code": "HANG\nwhile True:\n    pass\n"},
        ).json()
        self.assertEqual(hang["outcome"], "TIMEOUT")
        self.assertIsNone(hang["verification"])

    def test_client_cannot_spoof_server_truth(self):
        client = _client()
        session_id = _new_session(client)["session_id"]
        body = client.post(
            "/student/submissions",
            json={
                "session_id": session_id,
                "problem_id": CANONICAL_ID,
                "code": WRONG_CODE,
                # Spoofed server-side concepts: must be ignored, never trusted.
                "concept_id": "C8",
                "language_track": "java",
                "mastery": 1.0,
                "diagnosis": {"misconception_id": "C8-M01"},
                "verification": {"outcome": "VERIFIED_IMPROVED"},
                "recommendation": {"action": "CHALLENGE_PROBLEM"},
            },
        ).json()
        self.assertEqual(body["outcome"], "FAILED")
        self.assertEqual(body["diagnosis"]["misconception_id"], "C3-M01")
        self.assertNotIn("mastery", body)
        self.assertFalse(body["journey_state"]["mastery_claim"])

    def test_sessions_are_isolated(self):
        client = _client()
        first = _new_session(client)["session_id"]
        second = _new_session(client)["session_id"]
        self.assertNotEqual(first, second)
        client.post(
            "/student/submissions",
            json={"session_id": first, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        untouched = client.get("/student/journey", params={"session_id": second}).json()
        self.assertEqual(untouched["journey_state"]["stage"], "started")


class StudentOrchestrationTests(unittest.TestCase):
    def test_no_duplicated_intelligence_logic(self):
        """student.py orchestrates existing APIs; it reimplements nothing."""
        import ast as _ast

        tree = _ast.parse(
            (_APP_DIR / "student.py").read_text(encoding="utf-8"),
            filename="student.py",
        )
        called: set[str] = set()
        defined: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                defined.add(node.name)
            if isinstance(node, _ast.Call):
                func = node.func
                if isinstance(func, _ast.Name):
                    called.add(func.id)
                elif isinstance(func, _ast.Attribute):
                    called.add(func.attr)
        duplicated = {
            # mastery formula internals (packages.mastery owns these)
            "compute_mastery_update",
            "severity_for_status",
            "mastery_band",
            "compute_trend",
            "hint_dependence_rate",
            "transfer_success_rate",
            "is_transfer_variant",
            "check_recurring",
            "has_improved",
            "recent_occurrence_count",
            "isomorphic_variant_count",
            # adaptive policy internals (packages.adaptive owns these)
            "evaluate_concept",
            "evaluate_all",
            "rank_recommendations",
            "rank_key",
            "urgency_bonus",
            # diagnosis internals (ai-service owns these; the public
            # diagnose/build_intervention APIs are called, not redefined)
            "fallback_diagnose",
            "validate_llm_diagnosis",
            "confidence_grounding_gate",
            "build_diagnosis_prompt",
            # evidence internals (packages.evidence owns these)
            "build_evidence_pack",
            "normalize_output",
            # verification internals (packages.verification owns the table)
            "build_reason",
            "build_evidence",
            "to_learner_evidence",
        }
        hits = (called | defined) & duplicated
        self.assertEqual(hits, set(), f"student duplicates logic: {hits}")

    def test_orchestration_calls_every_required_api(self):
        import ast as _ast

        tree = _ast.parse(
            (_APP_DIR / "student.py").read_text(encoding="utf-8"),
            filename="student.py",
        )
        called: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call):
                func = node.func
                if isinstance(func, _ast.Name):
                    called.add(func.id)
                elif isinstance(func, _ast.Attribute):
                    called.add(func.attr)
        required = {
            "load_problem",  # bank
            "execute_problem",  # execution (Step 5)
            "to_student_view",  # safe redaction
            "build_pack_for_submission",  # evidence (Step 6)
            "diagnose_evidence",  # diagnosis (Steps 7 + 15)
            "snapshot_for_evidence",  # learner read (Step 8)
            "record_attempt",  # learner write (Step 8)
            "get_concept_view",
            "get_misconception_view",
            "recommend_next_actions",  # adaptive (Step 9)
            "attempt_from_execution",
            "verify_improvement",  # verification (Step 10)
            "run_closed_loop",  # closed loop (Step 11)
        }
        missing = required - called
        self.assertEqual(missing, set(), f"student bypasses APIs: {missing}")


if __name__ == "__main__":
    unittest.main()
