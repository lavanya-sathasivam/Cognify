"""Unit tests for Step 11: Closed-Loop Learner Integration (core-backend).

Covers: VERIFIED_IMPROVED / SURFACE_FIX / NOT_IMPROVED / INCOMPLETE flows
through the existing Step 8 learner engine, language isolation, metadata
validation, misconception + transfer preservation, Step 9 delegation
(behavioral equality, no duplicated policy/formula), determinism, and the
pure planning layer.

Run from repo root:
    python -m unittest discover -s services/core-backend/tests -t . -v

NOTE: ``services/core-backend`` is not importable (hyphen), so this file
bootstraps sys.path with the repo root AND the service dir.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
_SERVICE_DIR = _ROOT / "services" / "core-backend"
for _p in (str(_ROOT), str(_SERVICE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app import closed_loop  # noqa: E402
from app import learner_engine  # noqa: E402
from app import repositories  # noqa: E402
from app.closed_loop import (  # noqa: E402
    ClosedLoopContext,
    ClosedLoopResult,
    LearnerStateSnapshot,
    plan_records,
    run_closed_loop,
)
from app.db import get_engine, get_session_factory, init_db  # noqa: E402
from packages.adaptive import (  # noqa: E402
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    Recommendation,
    recommend_next_actions,
)
from packages.verification import (  # noqa: E402
    VerificationAttempt,
    VerificationContext,
    VerificationOutcome,
    verify_improvement,
)

CONCEPT = "C3"
TARGET = "C3-M01"
ORIG = "PY-C3-001"
TRANS = "PY-C3-002"
GROUP = "ISO-C3-01"

PROBLEMS = [
    {
        "problem_id": ORIG,
        "concept_id": CONCEPT,
        "difficulty": 2,
        "isomorphic_group_id": GROUP,
        "variant_role": "canonical",
    },
    {
        "problem_id": TRANS,
        "concept_id": CONCEPT,
        "difficulty": 2,
        "isomorphic_group_id": GROUP,
        "variant_role": "transfer",
    },
]


def _fresh_session(testcase):
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    factory = get_session_factory(engine)
    session = factory()
    testcase.addCleanup(session.close)
    return session


def _user_journey(session, track="python"):
    user = repositories.create_user(session)
    journey = repositories.create_journey(session, user.id, track)
    return user, journey


def _vresult(original_outcome=None, transfer_outcome=None, target=TARGET,
             group=GROUP, track="python"):
    """Build a Step 10 VerificationResult through the real Step 10 API."""
    original = None
    if original_outcome is not None:
        original = VerificationAttempt(
            problem_id=ORIG, concept_id=CONCEPT, language_track=track,
            outcome=original_outcome,
        )
    transfer = None
    if transfer_outcome is not None:
        transfer = VerificationAttempt(
            problem_id=TRANS, concept_id=CONCEPT, language_track=track,
            outcome=transfer_outcome, is_transfer=True,
        )
    ctx = VerificationContext(
        original_problem_id=ORIG,
        transfer_problem_id=TRANS,
        concept_id=CONCEPT,
        language_track=track,
        target_misconception_id=target,
        original_retry=original,
        transfer=transfer,
        isomorphic_group_id=group,
    )
    return verify_improvement(ctx)


def _loop_ctx(user, journey, vresult, **overrides):
    kwargs = {
        "user_id": user.id,
        "journey_id": journey.id,
        "language_track": "python",
        "concept_id": CONCEPT,
        "problem_id": ORIG,
        "transfer_problem_id": TRANS,
        "verification_result": vresult,
        "problems": [dict(p) for p in PROBLEMS],
    }
    kwargs.update(overrides)
    return ClosedLoopContext(**kwargs)


class VerifiedImprovedTests(unittest.TestCase):
    def test_verified_improved_updates_learner_and_recommends(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "PASS")
        self.assertEqual(vresult.outcome, VerificationOutcome.VERIFIED_IMPROVED)
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        self.assertEqual(out.verification_outcome, VerificationOutcome.VERIFIED_IMPROVED)
        self.assertTrue(out.learner_updated)
        self.assertEqual(len(out.recorded_attempts), 2)
        kinds = [a.kind for a in out.recorded_attempts]
        self.assertEqual(kinds, ["original_retry", "transfer"])
        state = out.updated_state
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.attempt_count, 2)
        self.assertEqual(state.pass_count, 2)
        self.assertEqual(state.transfer_attempts, 1)
        self.assertEqual(state.transfer_successes, 1)
        self.assertGreater(state.mastery, 0.20)
        self.assertEqual(out.target_misconception_id, TARGET)
        self.assertGreater(len(out.recommendations), 0)
        for rec in out.recommendations:
            self.assertIsInstance(rec, Recommendation)


class SurfaceFixTests(unittest.TestCase):
    def test_surface_fix_preserves_unresolved_weakness(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "FAIL")
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        self.assertEqual(out.verification_outcome, VerificationOutcome.SURFACE_FIX)
        self.assertTrue(out.learner_updated)
        self.assertEqual(len(out.recorded_attempts), 2)
        state = out.updated_state
        assert state is not None
        self.assertEqual(state.attempt_count, 2)
        self.assertEqual(state.pass_count, 1)
        self.assertEqual(state.fail_count, 1)
        self.assertEqual(state.transfer_attempts, 1)
        self.assertEqual(state.transfer_successes, 0)
        # Unresolved weakness preserved: counter bumped, still active.
        counter = repositories.get_counter(session, journey.id, CONCEPT, TARGET)
        self.assertIsNotNone(counter)
        assert counter is not None
        self.assertEqual(counter.occurrence_count, 1)
        self.assertTrue(counter.active)
        # Never claim mastery from the original pass alone.
        self.assertNotEqual(state.band, "mastered")
        self.assertGreater(len(out.recommendations), 0)


class NotImprovedTests(unittest.TestCase):
    def test_not_improved_records_failure_and_recommends(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("FAIL", "PASS")
        self.assertEqual(vresult.outcome, VerificationOutcome.NOT_IMPROVED)
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        self.assertTrue(out.learner_updated)
        # Only the failed original retry is recorded (transfer ignored).
        self.assertEqual(len(out.recorded_attempts), 1)
        self.assertEqual(out.recorded_attempts[0].kind, "original_retry")
        self.assertFalse(out.recorded_attempts[0].passed)
        state = out.updated_state
        assert state is not None
        self.assertEqual(state.attempt_count, 1)
        self.assertEqual(state.fail_count, 1)
        counter = repositories.get_counter(session, journey.id, CONCEPT, TARGET)
        self.assertIsNotNone(counter)
        assert counter is not None
        self.assertEqual(counter.occurrence_count, 1)
        self.assertGreater(len(out.recommendations), 0)


class IncompleteTests(unittest.TestCase):
    def test_incomplete_causes_zero_mutation(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult(None, None)
        self.assertEqual(vresult.outcome, VerificationOutcome.INCOMPLETE)
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        self.assertEqual(out.verification_outcome, VerificationOutcome.INCOMPLETE)
        self.assertFalse(out.learner_updated)
        self.assertEqual(out.recorded_attempts, ())
        self.assertIsNone(out.updated_state)
        self.assertEqual(out.recommendations, ())
        self.assertEqual(
            out.reason,
            "Verification evidence is incomplete; learner state was not mutated.",
        )
        # Zero learner mutation: no state row, no events at all.
        self.assertIsNone(repositories.get_concept_state(session, journey.id, CONCEPT))
        self.assertEqual(repositories.list_events_for_journey(session, journey.id), [])

    def test_incomplete_pass_only_still_no_mutation(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", None)
        self.assertEqual(vresult.outcome, VerificationOutcome.INCOMPLETE)
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        self.assertFalse(out.learner_updated)
        self.assertEqual(repositories.list_events_for_journey(session, journey.id), [])


class IsolationTests(unittest.TestCase):
    def test_java_attempt_cannot_update_python_state(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session, track="python")
        vresult = _vresult("PASS", "PASS")
        with self.assertRaises(ValueError):
            run_closed_loop(
                session, _loop_ctx(user, journey, vresult, language_track="java")
            )
        # Journey-track mismatch is also rejected.
        _user2, java_journey = _user_journey(session, track="java")
        with self.assertRaises(ValueError):
            run_closed_loop(session, _loop_ctx(user, java_journey, vresult))
        self.assertEqual(repositories.list_events_for_journey(session, journey.id), [])

    def test_concept_mismatch_rejected(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "PASS")
        with self.assertRaises(ValueError):
            _loop_ctx(user, journey, vresult, concept_id="C4")
        # Contradictory catalog metadata rejected.
        bad_problems = [dict(PROBLEMS[0], concept_id="C4"), dict(PROBLEMS[1])]
        with self.assertRaises(ValueError):
            _loop_ctx(user, journey, vresult, problems=bad_problems)
        with self.assertRaises(ValueError):
            _loop_ctx(
                user, journey, vresult,
                curriculum=CurriculumInfo.from_taxonomy("C4"),
            )

    def test_problem_id_mismatch_rejected(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "PASS")
        with self.assertRaises(ValueError):
            _loop_ctx(user, journey, vresult, problem_id="PY-C3-999")
        with self.assertRaises(ValueError):
            _loop_ctx(user, journey, vresult, transfer_problem_id="PY-C3-999")

    def test_run_rejects_non_context(self):
        session = _fresh_session(self)
        with self.assertRaises(TypeError):
            run_closed_loop(session, {"not": "a context"})  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            plan_records("nope")  # type: ignore[arg-type]


class PreservationTests(unittest.TestCase):
    def test_verification_misconception_preserved(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "FAIL")
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        self.assertEqual(out.target_misconception_id, TARGET)
        # Clean passes carry the target in evidence refs (auditable context).
        for attempt_events in (
            repositories.list_events_for_journey(
                session, journey.id, event_type="attempt", concept_id=CONCEPT
            )
        ):
            refs = (attempt_events.event_metadata or {}).get("evidence_refs", [])
            self.assertIn(f"verification-target:{TARGET}", refs)

    def test_transfer_evidence_preserved(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "PASS")
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        assert out.updated_state is not None
        self.assertEqual(out.updated_state.transfer_attempts, 1)
        self.assertEqual(out.updated_state.transfer_successes, 1)
        attempts = repositories.list_events_for_journey(
            session, journey.id, event_type="attempt", concept_id=CONCEPT
        )
        self.assertEqual(len(attempts), 2)
        by_problem = {e.event_metadata["problem_id"]: e for e in attempts}
        transfer_event = by_problem[TRANS]
        self.assertTrue(transfer_event.event_metadata["is_transfer"])
        self.assertEqual(transfer_event.event_metadata["variant_role"], "transfer")
        self.assertEqual(transfer_event.event_metadata["isomorphic_group_id"], GROUP)
        original_event = by_problem[ORIG]
        self.assertFalse(original_event.event_metadata["is_transfer"])
        self.assertEqual(original_event.event_metadata["variant_role"], "canonical")

    def test_iso_fallback_deterministic_without_group(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "PASS", group=None)
        self.assertIsNone(vresult.isomorphic_group_id)
        out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        self.assertTrue(out.learner_updated)
        attempts = repositories.list_events_for_journey(
            session, journey.id, event_type="attempt", concept_id=CONCEPT
        )
        groups = {e.event_metadata["isomorphic_group_id"] for e in attempts}
        self.assertEqual(len(groups), 1)
        fallback = groups.pop()
        self.assertTrue(fallback.startswith("CLOSED-LOOP-"))
        # Deterministic: identical rerun on a fresh DB yields the same group.
        session2 = _fresh_session(self)
        user2, journey2 = _user_journey(session2)
        out2 = run_closed_loop(session2, _loop_ctx(user2, journey2, vresult))
        attempts2 = repositories.list_events_for_journey(
            session2, journey2.id, event_type="attempt", concept_id=CONCEPT
        )
        self.assertEqual(
            {e.event_metadata["isomorphic_group_id"] for e in attempts2},
            {fallback},
        )
        self.assertEqual(out.to_dict()["recorded_attempts"],
                         out2.to_dict()["recorded_attempts"])

    def test_no_mastery_claim_in_reasons(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        for original, transfer in (("PASS", "PASS"), ("PASS", "FAIL"), ("FAIL", None)):
            vresult = _vresult(original, transfer)
            out = run_closed_loop(session, _loop_ctx(user, journey, vresult))
            lowered = out.reason.lower()
            self.assertNotIn("mastery achieved", lowered)
            self.assertNotIn("mastered the concept", lowered)


class Step9DelegationTests(unittest.TestCase):
    def test_recommendations_equal_direct_step9_call(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "PASS")
        ctx = _loop_ctx(user, journey, vresult)
        out = run_closed_loop(session, ctx)
        # Rebuild the exact Step 9 inputs from post-update Step 8 views.
        concept_view = learner_engine.get_concept_view(session, journey.id, CONCEPT)
        misc_view = learner_engine.get_misconception_view(
            session, journey.id, CONCEPT, TARGET
        )
        expected = recommend_next_actions(
            [ConceptState.from_learner_view(concept_view)],
            [MisconceptionState.from_misconception_view(misc_view)],
            [CurriculumInfo.from_taxonomy(CONCEPT)],
            list(ctx.problems or ()),
            language_track="python",
        )
        self.assertEqual(list(out.recommendations), expected)

    def test_no_duplicated_adaptive_policy(self):
        source = Path(closed_loop.__file__).read_text(encoding="utf-8")
        for marker in (
            "evaluate_concept", "evaluate_all", "BASE_PRIORITY", "urgency_bonus",
            "rank_recommendations", "rank_key", "REVIEW_CONCEPT",
            "REMEDIAL_PROBLEM", "is_transfer_ready", "is_challenge_ready",
            "TRANSFER_MIN_ATTEMPTS", "HIGH_HINT_THRESHOLD",
        ):
            self.assertNotIn(marker, source, f"closed_loop must not contain {marker!r}")


class NoDuplicatedMasteryTests(unittest.TestCase):
    def test_no_duplicated_mastery_formula(self):
        import re

        source = Path(closed_loop.__file__).read_text(encoding="utf-8")
        # No import of the formula package (docstring *mentions* are fine;
        # only real import statements count).
        self.assertIsNone(
            re.search(r"^\s*(import|from)\s+[^\n]*mastery", source, re.MULTILINE),
            "closed_loop must not import packages.mastery",
        )
        # No calls to formula internals (trailing paren = real usage).
        for marker in (
            "compute_mastery_update(", "PASS_BASE_GAIN", "TRANSFER_BONUS",
            "HINT_DAMPING", "FAIL_BASE_PENALTY", "FAIL_SEVERITY_SCALE",
            "severity_for_status(", "clamp_mastery(", "MOMENTUM_SCALE",
            "compute_trend(", "recent_pass_rate(",
        ):
            self.assertNotIn(marker, source, f"closed_loop must not contain {marker!r}")

    def test_mastery_matches_manual_step8_sequence(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        vresult = _vresult("PASS", "FAIL")
        ctx = _loop_ctx(user, journey, vresult)
        out = run_closed_loop(session, ctx)
        # Manual Step 8 sequence with the same planned records.
        session2 = _fresh_session(self)
        user2, journey2 = _user_journey(session2)
        for plan in plan_records(ctx):
            learner_engine.record_attempt(
                session2,
                user_id=user2.id,
                journey_id=journey2.id,
                concept_id=CONCEPT,
                problem_id=plan.problem_id,
                isomorphic_group_id=plan.isomorphic_group_id,
                variant_role=plan.variant_role,
                passed=plan.passed,
                execution_status=plan.execution_status,
                diagnosed_misconception_id=plan.diagnosed_misconception_id,
                diagnostic_confidence=plan.diagnostic_confidence,
                hint_used=plan.hint_used,
                evidence_refs=list(plan.evidence_refs),
                is_transfer=plan.is_transfer,
            )
        view = learner_engine.get_concept_view(session2, journey2.id, CONCEPT)
        manual = LearnerStateSnapshot.from_concept_view(view)
        assert out.updated_state is not None
        self.assertEqual(out.updated_state, manual)


class PurePlanningTests(unittest.TestCase):
    def test_plan_counts_per_outcome(self):
        self.assertEqual(len(plan_records(_ctx_only("PASS", "PASS"))), 2)
        self.assertEqual(len(plan_records(_ctx_only("PASS", "FAIL"))), 2)
        self.assertEqual(len(plan_records(_ctx_only("FAIL", None))), 1)
        self.assertEqual(plan_records(_ctx_only(None, None)), ())

    def test_plans_carry_transfer_semantics(self):
        plans = plan_records(_ctx_only("PASS", "FAIL"))
        original, transfer = plans
        self.assertEqual((original.kind, original.variant_role, original.is_transfer),
                         ("original_retry", "canonical", False))
        self.assertTrue(original.passed)
        self.assertIsNone(original.diagnosed_misconception_id)
        self.assertEqual((transfer.kind, transfer.variant_role, transfer.is_transfer),
                         ("transfer", "transfer", True))
        self.assertFalse(transfer.passed)
        self.assertEqual(transfer.diagnosed_misconception_id, TARGET)
        self.assertEqual(original.isomorphic_group_id, transfer.isomorphic_group_id)


def _ctx_only(original, transfer):
    """ClosedLoopContext without a DB (ids are placeholders for pure tests)."""
    return ClosedLoopContext(
        user_id=1,
        journey_id=1,
        language_track="python",
        concept_id=CONCEPT,
        problem_id=ORIG,
        transfer_problem_id=TRANS,
        verification_result=_vresult(original, transfer),
        problems=[dict(p) for p in PROBLEMS],
    )


class DeterminismTests(unittest.TestCase):
    def test_repeated_integration_is_identical(self):
        vresult = _vresult("PASS", "PASS")
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        first = run_closed_loop(session, _loop_ctx(user, journey, vresult))
        session2 = _fresh_session(self)
        user2, journey2 = _user_journey(session2)
        second = run_closed_loop(session2, _loop_ctx(user2, journey2, vresult))
        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_result_is_immutable(self):
        import dataclasses

        session = _fresh_session(self)
        user, journey = _user_journey(session)
        out = run_closed_loop(session, _loop_ctx(user, journey, _vresult("PASS", "PASS")))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            out.learner_updated = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
