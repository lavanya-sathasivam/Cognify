"""COGNIFY problem_bank — end-to-end adaptive learning journey (Step 14).

ORCHESTRATION ONLY. This module contains no intelligence: no mastery
formula, no misconception rules, no adaptive rules, no verification
rules, no execution logic, no evidence construction, no diagnosis
policy. Every stage delegates to an existing Steps 6-13 API:

    bank loader (Step 12/13)
      -> ``evaluator.evaluate`` + scripted ``PythonRunner`` (Step 5)
      -> ``build_evidence_pack`` (Step 6)
      -> ``diagnose_pack`` with ``client=None`` (Step 7 fallback)
      -> ``learner_engine.record_attempt`` (Step 8)
      -> ``recommend_next_actions`` (Step 9, intervention)
      -> retry + transfer executions (Step 5 again)
      -> ``verify_improvement`` (Step 10)
      -> ``run_closed_loop`` (Step 11: Step 8 writes + Step 9 ranking)
      -> ``recommend_next_actions`` once more, rebuilt from the updated
         Step 8 views, to prove the closed loop delegates to Step 9.

Demo scenario (deterministic, FakeSandboxRunner — the existing
deterministic test mechanism; no Docker, no wall clock):

    A. wrong canonical submission (off-by-one: ``range(len(nums) - 1)``)
       -> FAILED with real failed-test evidence
    B. corrected canonical submission -> PASSED (original retry)
    C. correct transfer submission -> PASSED
       -> VERIFIED_IMPROVED -> learner update -> next recommendations

Failure policy: stages never swallow errors. Unexpected outcomes raise
``JourneyStageError`` (or propagate the existing validators' errors), so
a broken journey fails loudly instead of reporting success.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.adaptive import (
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    ProblemInfo,
    Recommendation,
    recommend_next_actions,
)
from packages.problem_bank import loader as bank_loader
from packages.problem_bank import pipeline as pipe
from packages.verification import (
    VerificationContext,
    VerificationOutcome,
    verify_improvement,
)

CANONICAL_ID: str = "PY-C3-COUNT-DIV"
TRANSFER_ID: str = "PY-C3-COUNT-DIV-TRANSFER"
PROBE_ID: str = "PY-C3-LOOP-MISCONCEPTION"
CONCEPT_ID: str = "C3"
LANGUAGE_TRACK: str = "python"

# ---------------------------------------------------------------------------
# Deterministic demo submissions (real, runnable scripts; executed only
# through the existing execution-service sandbox abstraction).
# ---------------------------------------------------------------------------
_MAIN_TAIL: str = (
    "\n\ndef main():\n"
    "    import sys\n"
    "    data = sys.stdin.read().strip().split()\n"
    "    if not data:\n"
    "        return\n"
    "    n = int(data[0])\n"
    "    k = int(data[1])\n"
    "    nums = list(map(int, data[2:2 + n]))\n"
    "    print(count_divisible(nums, k))\n"
    "\n\nif __name__ == \"__main__\":\n"
    "    main()\n"
)

# Submission A — intentional off-by-one: the last element is never visited.
SUBMISSION_A_WRONG: str = (
    "def count_divisible(nums, k):\n"
    '    """Return how many numbers in nums are divisible by k."""\n'
    "    count = 0\n"
    "    for i in range(len(nums) - 1):\n"
    "        if nums[i] % k == 0:\n"
    "            count += 1\n"
    "    return count\n" + _MAIN_TAIL
)

# Submission B — corrected canonical solution.
SUBMISSION_B_FIXED: str = (
    "def count_divisible(nums, k):\n"
    '    """Return how many numbers in nums are divisible by k."""\n'
    "    count = 0\n"
    "    for x in nums:\n"
    "        if x % k == 0:\n"
    "            count += 1\n"
    "    return count\n" + _MAIN_TAIL
)

# Submission C — correct transfer solution (strict threshold comparison).
SUBMISSION_C_TRANSFER: str = (
    "def count_cold_days(temps, threshold):\n"
    '    """Return how many temperatures are strictly below threshold."""\n'
    "    count = 0\n"
    "    for t in temps:\n"
    "        if t < threshold:\n"
    "            count += 1\n"
    "    return count\n"
    "\n\ndef main():\n"
    "    import sys\n"
    "    data = sys.stdin.read().strip().split()\n"
    "    if not data:\n"
    "        return\n"
    "    n = int(data[0])\n"
    "    threshold = int(data[1])\n"
    "    temps = list(map(int, data[2:2 + n]))\n"
    "    print(count_cold_days(temps, threshold))\n"
    "\n\nif __name__ == \"__main__\":\n"
    "    main()\n"
)


class JourneyStageError(RuntimeError):
    """A journey stage did not produce its required outcome (fail loudly)."""


def _buggy_count_divisible(nums: list[int], k: int) -> int:
    """Pure mirror of Submission A's loop bug (drives the sandbox script).

    The script encodes what the existing Docker sandbox would return for
    the buggy code; it is derived here from the buggy logic applied to the
    problem's own test inputs — never hard-coded per test.
    """
    count = 0
    for i in range(len(nums) - 1):
        if nums[i] % k == 0:
            count += 1
    return count


def _wrong_handler(stdin_data: str, expected_output: str) -> str:
    parts = stdin_data.strip().split()
    n, k = int(parts[0]), int(parts[1])
    nums = list(map(int, parts[2:2 + n]))
    return str(_buggy_count_divisible(nums, k)) + "\n"


def _correct_handler(stdin_data: str, expected_output: str) -> str:
    return "correct"


def _problem_info_dict(problem: Any) -> dict[str, Any]:
    return {
        "problem_id": problem.problem_id,
        "concept_id": problem.concept_id,
        "difficulty": problem.difficulty,
        "isomorphic_group_id": problem.isomorphic_group_id,
        "variant_role": problem.variant_role,
    }


def _execution_summary(result: Any) -> dict[str, Any]:
    data = pipe.result_to_dict(result)
    return {
        "status": pipe.execution_status_str(result),
        "passed_count": data["passed_count"],
        "failed_count": data["failed_count"],
        "failed_test_id": data["failed_test_id"],
        "expected_output": data["expected_output"],
        "actual_output": data["actual_output"],
    }


@dataclass(frozen=True)
class LearningJourneyResult:
    """Immutable outcome of one complete adaptive learning journey."""

    problem_id: str
    initial_execution_outcome: str
    initial_execution: dict[str, Any]
    evidence_pack: dict[str, Any]
    diagnosis: dict[str, Any]
    intervention_recommendations: tuple[dict[str, Any], ...]
    retry_execution_outcome: str
    retry_execution: dict[str, Any]
    transfer_problem_id: str
    transfer_execution_outcome: str
    transfer_execution: dict[str, Any]
    verification_outcome: str
    verification: dict[str, Any]
    learner_updated: bool
    recorded_attempts: tuple[dict[str, Any], ...]
    learner_snapshot: dict[str, Any]
    next_recommendations: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping (no timestamps anywhere)."""
        return {
            "problem_id": self.problem_id,
            "initial_execution_outcome": self.initial_execution_outcome,
            "initial_execution": dict(self.initial_execution),
            "evidence_pack": dict(self.evidence_pack),
            "diagnosis": dict(self.diagnosis),
            "intervention_recommendations": list(self.intervention_recommendations),
            "retry_execution_outcome": self.retry_execution_outcome,
            "retry_execution": dict(self.retry_execution),
            "transfer_problem_id": self.transfer_problem_id,
            "transfer_execution_outcome": self.transfer_execution_outcome,
            "transfer_execution": dict(self.transfer_execution),
            "verification_outcome": self.verification_outcome,
            "verification": dict(self.verification),
            "learner_updated": self.learner_updated,
            "recorded_attempts": list(self.recorded_attempts),
            "learner_snapshot": dict(self.learner_snapshot),
            "next_recommendations": list(self.next_recommendations),
        }

    def summary(self) -> str:
        """Deterministic human-readable journey summary."""
        snap = self.learner_snapshot
        diag = self.diagnosis
        ver = self.verification
        lines = [
            f"Cognify learning journey ({CONCEPT_ID}, {LANGUAGE_TRACK}):",
            f"  canonical {self.problem_id}: initial "
            f"{self.initial_execution_outcome} "
            f"({self.initial_execution['failed_count']} failed, decisive "
            f"{self.initial_execution['failed_test_id']}) "
            f"-> retry {self.retry_execution_outcome}",
            f"  diagnosis: {diag['concept_id']} / {diag['misconception_id']} "
            f"({diag['source']}, confidence {diag['confidence']})",
            f"  intervention: {len(self.intervention_recommendations)} "
            "recommendation(s) from the adaptive engine: "
            + ", ".join(
                f"{r['action_type']}({r.get('problem_id')})"
                for r in self.intervention_recommendations
            ),
            f"  transfer {self.transfer_problem_id}: "
            f"{self.transfer_execution_outcome}",
            f"  verification: {self.verification_outcome} "
            f"({ver['reason_code']})",
            f"  learner: updated={self.learner_updated}, mastery "
            f"{snap['mastery']:.2f} ({snap['band']}), attempts "
            f"{snap['attempt_count']} ({snap['pass_count']} passed, "
            f"{snap['fail_count']} failed), transfer "
            f"{snap['transfer_successes']}/{snap['transfer_attempts']}",
            f"  next: {len(self.next_recommendations)} recommendation(s): "
            + ", ".join(
                f"{r['action_type']}({r.get('problem_id')})"
                for r in self.next_recommendations
            ),
        ]
        return "\n".join(lines)


def run_learning_journey(*, llm_client: Any = None) -> LearningJourneyResult:
    """Run the full student journey; raise ``JourneyStageError`` on deviation.

    Args:
        llm_client: LLM client for diagnosis, or None for the existing
            deterministic fallback (the honest default in tests).
    """
    canonical = bank_loader.load_problem(CANONICAL_ID)
    transfer = bank_loader.load_problem(TRANSFER_ID)
    probe = bank_loader.load_problem(PROBE_ID)
    if canonical.isomorphic_group_id != transfer.isomorphic_group_id:
        raise JourneyStageError(
            "Bank invariant broken: canonical and transfer problems do not "
            f"share an isomorphic group ({canonical.isomorphic_group_id!r} vs "
            f"{transfer.isomorphic_group_id!r})."
        )

    core_db = pipe.core_service_module("db")
    core_repos = pipe.core_service_module("repositories")
    learner_engine = pipe.core_service_module("learner_engine")
    closed_loop = pipe.closed_loop_module()

    engine = core_db.get_engine("sqlite:///:memory:")
    core_db.init_db(engine)
    session = core_db.get_session_factory(engine)()
    try:
        user = core_repos.create_user(session)
        journey_row = core_repos.create_journey(session, user.id, LANGUAGE_TRACK)
        user_id, journey_id = user.id, journey_row.id

        # -- Stage 1-3: wrong submission -> genuine FAILED execution -------
        wrong_result = pipe.execute_problem(
            canonical,
            SUBMISSION_A_WRONG,
            pipe.make_scripted_python_runner(
                pipe.script_for_outputs(canonical, _wrong_handler)
            ),
        )
        wrong_status = pipe.execution_status_str(wrong_result)
        if wrong_status != "FAILED":
            raise JourneyStageError(
                "Initial submission did not fail as the scenario requires: "
                f"status={wrong_status}."
            )

        # -- Stage 4: EvidencePack from real execution + real snapshot -----
        snapshot = learner_engine.snapshot_for_evidence(
            session, user_id, journey_id, CONCEPT_ID
        )
        pack = pipe.build_pack_for_submission(
            SUBMISSION_A_WRONG, canonical, wrong_result, snapshot
        )
        if pack.failed_count == 0 or pack.failed_test_id is None:
            raise JourneyStageError(
                "EvidencePack carries no failure evidence; cannot continue."
            )

        # -- Stage 5: existing diagnosis (fallback when client is None) ----
        diagnosis = pipe.diagnose_evidence(pack, llm_client)
        if diagnosis.concept_id != CONCEPT_ID:
            raise JourneyStageError(
                f"Diagnosis concept {diagnosis.concept_id!r} is not {CONCEPT_ID}."
            )
        candidate_ids = [c.misconception_id for c in pack.misconception_candidates]
        if diagnosis.misconception_id not in candidate_ids:
            raise JourneyStageError(
                f"Diagnosed {diagnosis.misconception_id!r} is not a pack "
                f"candidate {candidate_ids}."
            )

        # -- Record the failed attempt through the existing Step 8 API -----
        learner_engine.record_attempt(
            session,
            user_id=user_id,
            journey_id=journey_id,
            concept_id=CONCEPT_ID,
            problem_id=canonical.problem_id,
            isomorphic_group_id=canonical.isomorphic_group_id,
            variant_role=canonical.variant_role,
            passed=False,
            execution_status=wrong_status,
            diagnosed_misconception_id=diagnosis.misconception_id,
            diagnostic_confidence=diagnosis.confidence,
            hint_used=False,
            evidence_refs=list(diagnosis.evidence_refs),
            is_transfer=False,
        )

        # -- Stage 6: intervention from the existing adaptive engine -------
        catalog = [ProblemInfo.from_dict(_problem_info_dict(p)) for p in (
            canonical, transfer, probe,
        )]
        concept_view = learner_engine.get_concept_view(
            session, journey_id, CONCEPT_ID
        )
        misc_view = learner_engine.get_misconception_view(
            session, journey_id, CONCEPT_ID, diagnosis.misconception_id
        )
        intervention = recommend_next_actions(
            [ConceptState.from_learner_view(concept_view)],
            [MisconceptionState.from_misconception_view(misc_view)],
            [CurriculumInfo.from_taxonomy(CONCEPT_ID)],
            catalog,
            language_track=LANGUAGE_TRACK,
        )
        if not intervention or not all(
            isinstance(r, Recommendation) for r in intervention
        ):
            raise JourneyStageError(
                "Adaptive engine produced no intervention recommendations."
            )

        # -- Stages 7-8: corrected retry must genuinely PASS ---------------
        retry_result = pipe.execute_problem(
            canonical,
            SUBMISSION_B_FIXED,
            pipe.make_scripted_python_runner(
                pipe.script_for_outputs(canonical, _correct_handler)
            ),
        )
        if pipe.execution_status_str(retry_result) != "PASSED":
            raise JourneyStageError("Canonical retry did not pass.")

        # -- Stages 9-11: transfer must genuinely PASS ---------------------
        transfer_result = pipe.execute_problem(
            transfer,
            SUBMISSION_C_TRANSFER,
            pipe.make_scripted_python_runner(
                pipe.script_for_outputs(transfer, _correct_handler)
            ),
        )
        if pipe.execution_status_str(transfer_result) != "PASSED":
            raise JourneyStageError("Transfer submission did not pass.")

        # -- Stage 12: verification from the ACTUAL outcomes ---------------
        verification_context = VerificationContext(
            original_problem_id=canonical.problem_id,
            transfer_problem_id=transfer.problem_id,
            concept_id=CONCEPT_ID,
            language_track=LANGUAGE_TRACK,
            target_misconception_id=diagnosis.misconception_id,
            original_retry=pipe.attempt_from_execution(
                canonical,
                retry_result,
                misconception_id=diagnosis.misconception_id,
            ),
            transfer=pipe.attempt_from_execution(
                transfer, transfer_result, is_transfer=True
            ),
            isomorphic_group_id=canonical.isomorphic_group_id,
        )
        verification_result = verify_improvement(verification_context)
        if verification_result.outcome is not VerificationOutcome.VERIFIED_IMPROVED:
            raise JourneyStageError(
                "Verification did not return VERIFIED_IMPROVED: "
                f"{verification_result.outcome}."
            )

        # -- Stage 13: existing closed-loop integration (Step 8 + Step 9) --
        loop_context = closed_loop.ClosedLoopContext(
            user_id=user_id,
            journey_id=journey_id,
            language_track=LANGUAGE_TRACK,
            concept_id=CONCEPT_ID,
            problem_id=canonical.problem_id,
            transfer_problem_id=transfer.problem_id,
            verification_result=verification_result,
            problems=catalog,
        )
        loop_result = closed_loop.run_closed_loop(session, loop_context)
        if not loop_result.learner_updated:
            raise JourneyStageError(
                "Closed loop did not update the learner state."
            )

        # -- Stage 14: prove Step 9 delegation with a direct call ----------
        concept_view2 = learner_engine.get_concept_view(
            session, journey_id, CONCEPT_ID
        )
        misc_view2 = learner_engine.get_misconception_view(
            session, journey_id, CONCEPT_ID, diagnosis.misconception_id
        )
        direct = recommend_next_actions(
            [ConceptState.from_learner_view(concept_view2)],
            [MisconceptionState.from_misconception_view(misc_view2)],
            [CurriculumInfo.from_taxonomy(CONCEPT_ID)],
            catalog,
            language_track=LANGUAGE_TRACK,
        )
        if list(loop_result.recommendations) != direct:
            raise JourneyStageError(
                "Closed-loop recommendations diverge from a direct Step 9 call."
            )
        if not loop_result.recommendations:
            raise JourneyStageError(
                "Adaptive engine produced no next recommendations."
            )

        return LearningJourneyResult(
            problem_id=canonical.problem_id,
            initial_execution_outcome=wrong_status,
            initial_execution=_execution_summary(wrong_result),
            evidence_pack=pack.to_dict(),
            diagnosis=diagnosis.to_dict(),
            intervention_recommendations=tuple(
                r.to_dict() for r in intervention
            ),
            retry_execution_outcome=pipe.execution_status_str(retry_result),
            retry_execution=_execution_summary(retry_result),
            transfer_problem_id=transfer.problem_id,
            transfer_execution_outcome=pipe.execution_status_str(transfer_result),
            transfer_execution=_execution_summary(transfer_result),
            verification_outcome=verification_result.outcome.value,
            verification=verification_result.to_dict(),
            learner_updated=bool(loop_result.learner_updated),
            recorded_attempts=tuple(
                a.to_dict() for a in loop_result.recorded_attempts
            ),
            learner_snapshot=loop_result.updated_state.to_dict(),
            next_recommendations=tuple(
                r.to_dict() for r in loop_result.recommendations
            ),
        )
    finally:
        session.close()


def main() -> int:
    """Tiny CLI harness: run the journey and print its summary."""
    result = run_learning_journey()
    print(result.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANONICAL_ID",
    "CONCEPT_ID",
    "LANGUAGE_TRACK",
    "PROBE_ID",
    "SUBMISSION_A_WRONG",
    "SUBMISSION_B_FIXED",
    "SUBMISSION_C_TRANSFER",
    "TRANSFER_ID",
    "JourneyStageError",
    "LearningJourneyResult",
    "main",
    "run_learning_journey",
]
