"""Unit tests for Step 14: End-to-End Adaptive Learning Journey.

Proves ONE complete Cognify loop on real component contracts:

    canonical problem -> wrong submission -> FAILED execution
      -> EvidencePack -> fallback diagnosis (C3 + candidate misconception)
      -> Step 8 record_attempt -> Step 9 intervention recommendations
      -> corrected retry PASSED -> transfer PASSED
      -> VERIFIED_IMPROVED -> run_closed_loop learner update
      -> Step 9 next recommendations (equivalence-gated inside the journey)

Execution uses the EXISTING scripted FakeSandboxRunner mechanism (no
Docker, no wall clock). Nothing is hard-coded: the wrong submission's
outputs are cross-checked here by an INDEPENDENT re-implementation of
the buggy loop, and every verdict comes out of the existing services.
Diagnosis runs the existing fallback path (``client=None``) honestly —
no mock misconception is injected.

Run from repo root:
    python -m unittest discover -s packages/problem_bank/tests -t . -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# -- sys.path bootstrap (repo root only; pipeline alias-loads services) ----
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.problem_bank import journey as journey_mod  # noqa: E402
from packages.problem_bank import loader as bank_loader  # noqa: E402
from packages.problem_bank import pipeline as pipe  # noqa: E402
from packages.problem_bank.journey import (  # noqa: E402
    CANONICAL_ID,
    CONCEPT_ID,
    LANGUAGE_TRACK,
    TRANSFER_ID,
    JourneyStageError,
    LearningJourneyResult,
    SUBMISSION_A_WRONG,
    SUBMISSION_B_FIXED,
    SUBMISSION_C_TRANSFER,
    run_learning_journey,
)
from packages.verification import (  # noqa: E402
    VerificationContext,
    verify_improvement,
)


def _independent_buggy_outputs(problem) -> dict[str, str]:
    """Recompute Submission A's outputs with separate logic (cross-check)."""
    out: dict[str, str] = {}
    for case in problem.all_tests():
        parts = case.input.strip().split()
        n, k = int(parts[0]), int(parts[1])
        nums = list(map(int, parts[2:2 + n]))
        count = 0
        for i in range(len(nums) - 1):  # the off-by-one under test
            if nums[i] % k == 0:
                count += 1
        out[case.id] = str(count)
    return out


class JourneyStagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_learning_journey()
        cls.body = cls.result.to_dict()

    def test_canonical_problem_loads(self):
        problem = bank_loader.load_problem(CANONICAL_ID)
        self.assertEqual(problem.problem_id, self.result.problem_id)
        self.assertEqual(problem.concept_id, CONCEPT_ID)
        self.assertEqual(problem.language, LANGUAGE_TRACK)
        self.assertTrue(SUBMISSION_A_WRONG.strip())
        self.assertTrue(SUBMISSION_B_FIXED.strip())

    def test_intentional_wrong_submission_genuinely_fails(self):
        self.assertEqual(self.result.initial_execution_outcome, "FAILED")
        summary = self.result.initial_execution
        self.assertEqual(
            (summary["passed_count"], summary["failed_count"]), (2, 3)
        )
        self.assertEqual(summary["failed_test_id"], "P2")
        self.assertEqual(summary["expected_output"], "3")
        self.assertEqual(summary["actual_output"].strip(), "2")
        # Independent recomputation: every test's buggy output matches the
        # failed-test evidence (failures) and the passes (P1, H1).
        problem = bank_loader.load_problem(CANONICAL_ID)
        recomputed = _independent_buggy_outputs(problem)
        failed_ids = {t["test_id"] for t in self.body["evidence_pack"]["failed_tests"]}
        expected_by_id = {t.id: t.expected_output for t in problem.all_tests()}
        for tid, buggy in recomputed.items():
            if tid in failed_ids:
                self.assertNotEqual(buggy, expected_by_id[tid])
            else:
                self.assertEqual(buggy, expected_by_id[tid])
        self.assertEqual(failed_ids, {"P2", "H2", "H3"})

    def test_evidence_pack_contains_failure_evidence(self):
        pack = self.body["evidence_pack"]
        self.assertEqual(pack["problem_id"], CANONICAL_ID)
        self.assertEqual(pack["concept_id"], CONCEPT_ID)
        self.assertEqual(pack["execution_status"], "FAILED")
        self.assertEqual(pack["failed_count"], 3)
        self.assertEqual(pack["failed_test_id"], "P2")
        self.assertEqual(len(pack["failed_tests"]), 3)
        self.assertEqual(pack["evidence_kind"], "observed")
        self.assertIsNone(pack["confirmed_misconception_id"])

    def test_diagnosis_receives_that_evidence_pack(self):
        pack = self.body["evidence_pack"]
        diagnosis = self.body["diagnosis"]
        self.assertEqual(diagnosis["concept_id"], pack["concept_id"])
        self.assertIn(
            diagnosis["misconception_id"],
            [c["misconception_id"] for c in pack["misconception_candidates"]],
        )
        # The refs ground the diagnosis in the decisive failed test.
        self.assertIn(
            f"failed_test:{pack['failed_test_id']}", diagnosis["evidence_refs"]
        )

    def test_diagnosis_fallback_behavior_is_honest(self):
        diagnosis = self.body["diagnosis"]
        # No LLM is configured in tests, so the existing service answers
        # with its deterministic fallback classifier — reported, not hidden.
        self.assertEqual(diagnosis["source"], "fallback")
        self.assertEqual(diagnosis["concept_id"], "C3")
        canonical = bank_loader.load_problem(CANONICAL_ID)
        self.assertIn(
            diagnosis["misconception_id"], list(canonical.misconception_ids)
        )
        self.assertTrue(0.0 <= diagnosis["confidence"] <= 1.0)

    def test_intervention_comes_from_the_adaptive_engine(self):
        recs = self.body["intervention_recommendations"]
        self.assertGreater(len(recs), 0)
        for rec in recs:
            self.assertEqual(rec["concept_id"], "C3")
            self.assertTrue(rec["action_type"].strip())
            self.assertTrue(rec["reason"].strip())
            self.assertIsInstance(rec["supporting_evidence"], dict)

    def test_corrected_canonical_submission_genuinely_passes(self):
        self.assertEqual(self.result.retry_execution_outcome, "PASSED")
        summary = self.result.retry_execution
        self.assertEqual(
            (summary["passed_count"], summary["failed_count"]), (5, 0)
        )
        self.assertIsNone(summary["failed_test_id"])

    def test_transfer_problem_loads(self):
        problem = bank_loader.load_problem(TRANSFER_ID)
        self.assertEqual(problem.problem_id, self.result.transfer_problem_id)
        self.assertEqual(problem.concept_id, CONCEPT_ID)
        self.assertEqual(problem.language, LANGUAGE_TRACK)
        self.assertTrue(SUBMISSION_C_TRANSFER.strip())

    def test_transfer_submission_genuinely_passes(self):
        self.assertEqual(self.result.transfer_execution_outcome, "PASSED")
        summary = self.result.transfer_execution
        self.assertEqual(
            (summary["passed_count"], summary["failed_count"]), (5, 0)
        )
        self.assertIsNone(summary["failed_test_id"])

    def test_verification_returns_verified_improved(self):
        self.assertEqual(self.result.verification_outcome, "VERIFIED_IMPROVED")
        verification = self.body["verification"]
        self.assertEqual(verification["reason_code"], "ORIGINAL_AND_TRANSFER_PASSED")
        self.assertTrue(verification["original_passed"])
        self.assertTrue(verification["transfer_passed"])
        self.assertEqual(
            verification["target_misconception_id"],
            self.body["diagnosis"]["misconception_id"],
        )
        self.assertEqual(verification["concept_id"], "C3")
        self.assertTrue(len(verification["evidence"]) > 0)

    def test_learner_model_is_updated(self):
        self.assertTrue(self.result.learner_updated)
        snap = self.body["learner_snapshot"]
        self.assertEqual(snap["concept_id"], "C3")
        self.assertEqual(snap["language_track"], "python")
        # Three attempts reached the learner model: initial failure (Step 8
        # record) plus retry + transfer (closed loop).
        self.assertEqual(snap["attempt_count"], 3)
        self.assertEqual(snap["pass_count"], 2)
        self.assertEqual(snap["fail_count"], 1)
        self.assertEqual(snap["transfer_attempts"], 1)
        self.assertEqual(snap["transfer_successes"], 1)
        self.assertTrue(0.0 < snap["mastery"] < 1.0)
        # Step 8 owns the band verdict; the journey only reports it.
        self.assertEqual(snap["band"], "novice")

    def test_verification_evidence_is_preserved(self):
        recorded = self.body["recorded_attempts"]
        self.assertEqual(
            [a["kind"] for a in recorded], ["original_retry", "transfer"]
        )
        self.assertTrue(all(a["passed"] for a in recorded))
        by_kind = {a["kind"]: a for a in recorded}
        self.assertFalse(by_kind["original_retry"]["is_transfer"])
        self.assertTrue(by_kind["transfer"]["is_transfer"])
        self.assertEqual(
            by_kind["transfer"]["problem_id"], TRANSFER_ID
        )
        self.assertEqual(
            self.body["verification"]["target_misconception_id"],
            self.body["diagnosis"]["misconception_id"],
        )

    def test_adaptive_recommendations_are_produced(self):
        recs = self.body["next_recommendations"]
        self.assertGreater(len(recs), 0)
        for rec in recs:
            self.assertEqual(rec["concept_id"], "C3")
            self.assertTrue(rec["action_type"].strip())
        # The journey gates on Step 9 delegation internally: reaching this
        # result proves closed-loop output equalled a direct Step 9 call.

    def test_final_result_contains_the_complete_journey(self):
        body = self.body
        for key in (
            "problem_id",
            "initial_execution_outcome",
            "initial_execution",
            "evidence_pack",
            "diagnosis",
            "intervention_recommendations",
            "retry_execution_outcome",
            "retry_execution",
            "transfer_problem_id",
            "transfer_execution_outcome",
            "transfer_execution",
            "verification_outcome",
            "verification",
            "learner_updated",
            "recorded_attempts",
            "learner_snapshot",
            "next_recommendations",
        ):
            self.assertIn(key, body)
        summary = self.result.summary()
        self.assertTrue(summary.strip())
        for token in (
            CANONICAL_ID,
            TRANSFER_ID,
            "VERIFIED_IMPROVED",
            self.body["diagnosis"]["misconception_id"],
        ):
            self.assertIn(token, summary)

    def test_repeated_journey_is_deterministic(self):
        again = run_learning_journey()
        self.assertEqual(again.to_dict(), self.result.to_dict())
        self.assertEqual(again.summary(), self.result.summary())


class JourneyFailureStatesTests(unittest.TestCase):
    def test_missing_transfer_result_does_not_claim_verified_improved(self):
        canonical = bank_loader.load_problem(CANONICAL_ID)
        runner = pipe.make_scripted_python_runner(
            pipe.script_for_outputs(canonical, lambda stdin, expected: "correct")
        )
        retry_result = pipe.execute_problem(
            canonical, SUBMISSION_B_FIXED, runner
        )
        self.assertEqual(pipe.execution_status_str(retry_result), "PASSED")
        context = VerificationContext(
            original_problem_id=canonical.problem_id,
            transfer_problem_id=None,
            concept_id=canonical.concept_id,
            language_track=canonical.language,
            target_misconception_id=None,
            original_retry=pipe.attempt_from_execution(canonical, retry_result),
            transfer=None,
            isomorphic_group_id=canonical.isomorphic_group_id,
        )
        outcome = verify_improvement(context).outcome
        self.assertEqual(outcome.value, "INCOMPLETE")
        self.assertNotEqual(outcome.value, "VERIFIED_IMPROVED")

    def test_missing_problem_fails_clearly(self):
        with self.assertRaises(ValueError):
            bank_loader.load_problem("NO-SUCH-PROBLEM")

    def test_stage_errors_are_loud(self):
        self.assertTrue(issubclass(JourneyStageError, RuntimeError))
        self.assertIsInstance(
            LearningJourneyResult, type
        )  # result model exists as specified


class JourneyOrchestrationTests(unittest.TestCase):
    def _calls_in(self, path: Path) -> tuple[set[str], set[str]]:
        import ast

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        called: set[str] = set()
        defined: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
        return called, defined

    def test_no_duplicated_component_logic(self):
        """journey.py must call existing APIs, never reimplement them."""
        called, defined = self._calls_in(
            _ROOT / "packages" / "problem_bank" / "journey.py"
        )
        duplicated = {
            # mastery formula internals (Step 8 owns these)
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
            # adaptive policy internals (Step 9 owns these)
            "evaluate_concept",
            "evaluate_all",
            "rank_recommendations",
            "rank_key",
            "urgency_bonus",
            # diagnosis internals (Step 7 owns these)
            "fallback_diagnose",
            "validate_llm_diagnosis",
            "confidence_grounding_gate",
            "build_diagnosis_prompt",
            # evidence/execution internals (Steps 5-6 own these)
            "build_evidence_pack",
            "normalize_output",
            # verification internals (Step 10 owns the table)
            "build_reason",
            "build_evidence",
            "to_learner_evidence",
        }
        hits = (called | defined) & duplicated
        self.assertEqual(hits, set(), f"journey duplicates component logic: {hits}")

    def test_orchestration_calls_every_required_api(self):
        called, _ = self._calls_in(
            _ROOT / "packages" / "problem_bank" / "journey.py"
        )
        required = {
            "load_problem",  # bank (Steps 12-13)
            "execute_problem",  # execution (Step 5)
            "make_scripted_python_runner",
            "build_pack_for_submission",  # evidence (Step 6)
            "diagnose_evidence",  # diagnosis (Step 7)
            "record_attempt",  # learner model (Step 8)
            "snapshot_for_evidence",
            "get_concept_view",
            "get_misconception_view",
            "recommend_next_actions",  # adaptive (Step 9)
            "attempt_from_execution",
            "verify_improvement",  # verification (Step 10)
            "run_closed_loop",  # closed loop (Step 11)
        }
        missing = required - called
        self.assertEqual(missing, set(), f"journey bypasses APIs: {missing}")

    def test_result_model_is_immutable(self):
        import dataclasses

        result = run_learning_journey()
        self.assertIsInstance(result, LearningJourneyResult)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.problem_id = "TAMPERED"  # type: ignore[misc]

    def test_journey_module_exports(self):
        for name in (
            "run_learning_journey",
            "LearningJourneyResult",
            "JourneyStageError",
            "CANONICAL_ID",
            "TRANSFER_ID",
        ):
            self.assertTrue(hasattr(journey_mod, name), name)


if __name__ == "__main__":
    unittest.main()
