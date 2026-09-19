"""Unit tests for Step 8: Learner Model + Mastery Engine (core-backend).

Covers: initial state, successful/failed submissions, repeated
misconception + recurring weakness (all three rules), language isolation,
mastery boundaries, hint dependence, transfer success, improvement
detection, deterministic calculation, and mastery-transition history with
explainability. Also guards ownership (AI service never writes learner
state) and Step 6/7 non-regression (EvidencePack still builds).

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

from app import learner_engine  # noqa: E402
from app import repositories  # noqa: E402
from app.db import get_engine, get_session_factory, init_db  # noqa: E402
from packages.mastery import formula as mastery_formula  # noqa: E402


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


def _record(session, user, journey, **overrides):
    kwargs = {
        "user_id": user.id,
        "journey_id": journey.id,
        "concept_id": "C1",
        "problem_id": "PY-C1-001",
        "isomorphic_group_id": "ISO-C1-GRP",
        "variant_role": "canonical",
        "passed": False,
        "execution_status": "FAILED",
        "diagnosed_misconception_id": "C1-M01",
        "diagnostic_confidence": 0.7,
        "hint_used": False,
        "evidence_refs": ["failed_test:P1", "expected_output"],
        "is_transfer": None,
    }
    kwargs.update(overrides)
    return learner_engine.record_attempt(session, **kwargs)


class InitialStateTests(unittest.TestCase):
    def test_ensure_creates_point_two_zero_novice(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        state = learner_engine.ensure_concept_state(session, user.id, journey.id, "C1")
        self.assertAlmostEqual(float(state.mastery), 0.20)
        self.assertEqual(state.current_band, "novice")
        self.assertEqual(state.attempt_count, 0)
        self.assertEqual(state.successful_attempts, 0)
        self.assertEqual(state.hint_count, 0)
        self.assertEqual(state.transfer_attempts, 0)
        self.assertEqual(state.transfer_successes, 0)

    def test_concept_view_for_new_learner(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["mastery"], 0.20)
        self.assertEqual(view["band"], "novice")
        self.assertEqual(view["attempt_count"], 0)
        self.assertEqual(view["pass_count"], 0)
        self.assertEqual(view["fail_count"], 0)
        self.assertEqual(view["recent_performance"], {"last_5": [], "pass_rate": 0.0})
        self.assertEqual(view["trend"], "unknown")
        self.assertEqual(view["active_misconception_ids"], [])
        self.assertEqual(view["hint_dependence"], 0.0)
        self.assertEqual(view["transfer_success_rate"], 0.0)
        self.assertIsNone(view["last_attempted_at"])
        self.assertEqual(view["language_track"], "python")

    def test_misconception_view_unseen(self):
        session = _fresh_session(self)
        _user, journey = _user_journey(session)
        view = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertEqual(view["occurrence_count"], 0)
        self.assertEqual(view["recent_count"], 0)
        self.assertIsNone(view["last_seen_at"])
        self.assertFalse(view["active"])
        self.assertFalse(view["is_recurring"])
        self.assertFalse(view["is_improving"])

    def test_concept_normalized(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        state = learner_engine.ensure_concept_state(session, user.id, journey.id, " c1 ")
        self.assertEqual(state.concept_id, "C1")


class SuccessfulSubmissionTests(unittest.TestCase):
    def test_pass_increases_mastery_and_counts(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        out = _record(
            session, user, journey,
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None,
            diagnostic_confidence=None,
            evidence_refs=["execution_status", "code"],
        )
        t = out["transition"]
        self.assertGreater(t["new_mastery"], t["previous_mastery"])
        self.assertAlmostEqual(t["previous_mastery"], 0.20)
        self.assertAlmostEqual(t["new_mastery"], 0.32)
        self.assertAlmostEqual(t["delta"], 0.12)
        view = out["concept_view"]
        self.assertEqual(view["attempt_count"], 1)
        self.assertEqual(view["pass_count"], 1)
        self.assertEqual(view["fail_count"], 0)
        self.assertEqual(view["recent_performance"]["last_5"], [True])
        self.assertIsNotNone(view["last_attempted_at"])
        # Transition audit fields.
        for key in ("concept_id", "language_track", "previous_mastery",
                    "new_mastery", "delta", "reason", "evidence_refs", "timestamp"):
            self.assertIn(key, t)
        self.assertEqual(t["concept_id"], "C1")
        self.assertEqual(t["language_track"], "python")
        self.assertEqual(t["evidence_refs"], ["execution_status", "code"])

    def test_pass_without_hint_trend_stable_single(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        out = _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        self.assertEqual(out["concept_view"]["trend"], "stable")


class FailedSubmissionTests(unittest.TestCase):
    def test_fail_decreases_mastery_and_records_counter(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        out = _record(session, user, journey)
        t = out["transition"]
        self.assertLess(t["new_mastery"], t["previous_mastery"])
        self.assertAlmostEqual(t["previous_mastery"], 0.20)
        # FAILED severity 0.5, no hint, canonical, neutral momentum:
        # delta = -(0.05+0.07*0.5) = -0.085 -> 0.115
        self.assertAlmostEqual(t["new_mastery"], 0.115)
        view = out["concept_view"]
        self.assertEqual(view["attempt_count"], 1)
        self.assertEqual(view["pass_count"], 0)
        self.assertEqual(view["fail_count"], 1)
        self.assertEqual(view["active_misconception_ids"], ["C1-M01"])
        misc = out["misconception_view"]
        self.assertEqual(misc["occurrence_count"], 1)
        self.assertEqual(misc["recent_count"], 1)
        self.assertIsNotNone(misc["last_seen_at"])
        self.assertTrue(misc["active"])
        self.assertFalse(misc["is_recurring"])  # only once so far

    def test_timeout_penalized_more_than_wrong_output(self):
        s1 = _fresh_session(self)
        u1, j1 = _user_journey(s1)
        t_failed = _record(s1, u1, j1)["transition"]
        s2 = _fresh_session(self)
        u2, j2 = _user_journey(s2)
        t_timeout = _record(
            s2, u2, j2, execution_status="TIMEOUT",
            evidence_refs=["execution_status", "code"],
        )["transition"]
        self.assertLess(t_timeout["new_mastery"], t_failed["new_mastery"])


class RepeatedMisconceptionTests(unittest.TestCase):
    def test_second_occurrence_in_last_five_is_recurring(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        first = _record(session, user, journey, problem_id="PY-C1-001")
        self.assertFalse(first["is_recurring"])
        second = _record(session, user, journey, problem_id="PY-C1-002")
        self.assertTrue(second["is_recurring"])
        self.assertIn("last 5", second["recurring_reason"])
        view = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertEqual(view["occurrence_count"], 2)
        self.assertTrue(view["is_recurring"])

    def test_different_misconceptions_independent(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, diagnosed_misconception_id="C1-M01")
        out = _record(
            session, user, journey, problem_id="PY-C1-002",
            diagnosed_misconception_id="C1-M02",
        )
        v1 = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        v2 = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M02")
        self.assertEqual(v1["occurrence_count"], 1)
        self.assertEqual(v2["occurrence_count"], 1)
        self.assertFalse(v2["is_recurring"])
        self.assertFalse(out["is_recurring"])


class RecurringWeaknessTests(unittest.TestCase):
    def test_historical_three_plus_is_recurring(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        for i in range(3):
            _record(session, user, journey, problem_id=f"PY-C1-00{i+1}")
        view = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertEqual(view["occurrence_count"], 3)
        self.assertTrue(view["is_recurring"])

    def test_variant_rule_two_plus_variants(self):
        # Fail, then 4 clean passes, then fail on a different problem:
        # recent window holds only 1 occurrence but variants == 2 -> R3 fires.
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        for i in range(4):
            _record(
                session, user, journey, problem_id=f"PY-C1-P{i}",
                passed=True, execution_status="PASSED",
                diagnosed_misconception_id=None, diagnostic_confidence=None,
                evidence_refs=["code"],
            )
        out = _record(session, user, journey, problem_id="PY-C1-002")
        self.assertTrue(out["is_recurring"])
        self.assertIn("variant", out["recurring_reason"])
        view = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertEqual(view["distinct_variant_count"], 2)

    def test_single_occurrence_not_recurring(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        out = _record(session, user, journey)
        self.assertFalse(out["is_recurring"])
        self.assertIn("not recurring", out["recurring_reason"])


class R3IsomorphicGroupTests(unittest.TestCase):
    """Discriminating tests for R3: identity is isomorphic_group_id."""

    def _four_clean_passes(self, session, user, journey):
        for i in range(4):
            _record(
                session, user, journey, problem_id=f"PY-C1-P{i}",
                isomorphic_group_id="ISO-C1-PASS",
                passed=True, execution_status="PASSED",
                diagnosed_misconception_id=None, diagnostic_confidence=None,
                evidence_refs=["code"],
            )

    def test_different_groups_do_not_fire_r3(self):
        # Same misconception, 2 different problems, DIFFERENT groups.
        # Spaced by 4 passes so R1 (recent>=2) and R2 (total>=3) stay silent;
        # R3 must NOT fire because no single group holds 2 variants.
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, problem_id="PY-C1-001",
            isomorphic_group_id="ISO-C1-GRP-A",
        )
        self._four_clean_passes(session, user, journey)
        out = _record(
            session, user, journey, problem_id="PY-C1-002",
            isomorphic_group_id="ISO-C1-GRP-B",
        )
        self.assertFalse(out["is_recurring"])
        self.assertIn("not recurring", out["recurring_reason"])
        view = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertEqual(view["occurrence_count"], 2)
        self.assertEqual(view["recent_count"], 1)
        # Max per-group distinct problems is 1 (A:{P1}, B:{P2}).
        self.assertEqual(view["distinct_variant_count"], 1)
        self.assertFalse(view["is_recurring"])

    def test_same_group_fires_r3(self):
        # Same misconception, 2 different problems, SAME group.
        # R1/R2 still silent (recent==1, total==2); R3 MUST fire.
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, problem_id="PY-C1-001",
            isomorphic_group_id="ISO-C1-SAME",
        )
        self._four_clean_passes(session, user, journey)
        out = _record(
            session, user, journey, problem_id="PY-C1-002",
            isomorphic_group_id="ISO-C1-SAME",
        )
        self.assertTrue(out["is_recurring"])
        self.assertIn("variant", out["recurring_reason"])
        view = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertEqual(view["distinct_variant_count"], 2)
        self.assertTrue(view["is_recurring"])

    def test_r1_and_r2_unchanged_by_group_fix(self):
        # R1: 2 recent occurrences fire regardless of groups.
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, problem_id="PY-C1-001",
            isomorphic_group_id="ISO-C1-GRP-A",
        )
        out = _record(
            session, user, journey, problem_id="PY-C1-002",
            isomorphic_group_id="ISO-C1-GRP-B",
        )
        self.assertTrue(out["is_recurring"])
        self.assertIn("last 5", out["recurring_reason"])
        # R2: 3 historical occurrences fire regardless of groups.
        session2 = _fresh_session(self)
        user2, journey2 = _user_journey(session2)
        for i, grp in enumerate(["ISO-C1-G1", "ISO-C1-G2", "ISO-C1-G3"]):
            _record(
                session2, user2, journey2, problem_id=f"PY-C1-0{i+1}",
                isomorphic_group_id=grp,
            )
        view2 = learner_engine.get_misconception_view(
            session2, journey2.id, "C1", "C1-M01"
        )
        self.assertEqual(view2["occurrence_count"], 3)
        self.assertTrue(view2["is_recurring"])


class LanguageIsolationTests(unittest.TestCase):
    def test_python_and_java_never_share_state(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        py = repositories.create_journey(session, user.id, "python")
        java = repositories.create_journey(session, user.id, "java")
        _record(session, user, py, problem_id="PY-C1-001")
        _record(session, user, py, problem_id="PY-C1-002")
        py_view = learner_engine.get_concept_view(session, py.id, "C1")
        java_view = learner_engine.get_concept_view(session, java.id, "C1")
        self.assertEqual(py_view["attempt_count"], 2)
        self.assertEqual(java_view["attempt_count"], 0)
        self.assertEqual(java_view["mastery"], 0.20)
        self.assertNotEqual(py_view["mastery"], java_view["mastery"])
        self.assertEqual(java_view["active_misconception_ids"], [])
        # Counters scoped per journey.
        py_counters = repositories.list_counters_for_journey(session, py.id)
        java_counters = repositories.list_counters_for_journey(session, java.id)
        self.assertEqual(len(py_counters), 1)
        self.assertEqual(len(java_counters), 0)
        # Events scoped per journey.
        self.assertEqual(len(repositories.list_events_for_journey(session, py.id)), 7)
        self.assertEqual(len(repositories.list_events_for_journey(session, java.id)), 0)

    def test_transition_carries_track(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        java = repositories.create_journey(session, user.id, "java")
        out = learner_engine.record_attempt(
            session, user_id=user.id, journey_id=java.id, concept_id="C2",
            problem_id="JAVA-C2-001", isomorphic_group_id="ISO-C2-GRP",
            variant_role="canonical", passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, evidence_refs=["code"],
        )
        self.assertEqual(out["transition"]["language_track"], "java")

    def test_cross_user_journey_rejected(self):
        session = _fresh_session(self)
        user_a = repositories.create_user(session)
        user_b = repositories.create_user(session)
        journey_a = repositories.create_journey(session, user_a.id, "python")
        with self.assertRaises(ValueError):
            learner_engine.record_attempt(
                session, user_id=user_b.id, journey_id=journey_a.id,
                concept_id="C1", problem_id="PY-C1-001",
                isomorphic_group_id="ISO-C1-GRP", variant_role="canonical",
                passed=False, execution_status="FAILED",
                diagnosed_misconception_id="C1-M01",
                evidence_refs=["code"],
            )


class MasteryBoundaryTests(unittest.TestCase):
    def test_bands_match_spec(self):
        self.assertEqual(mastery_formula.mastery_band(0.39), "novice")
        self.assertEqual(mastery_formula.mastery_band(0.40), "emerging")
        self.assertEqual(mastery_formula.mastery_band(0.59), "emerging")
        self.assertEqual(mastery_formula.mastery_band(0.60), "proficient")
        self.assertEqual(mastery_formula.mastery_band(0.79), "proficient")
        self.assertEqual(mastery_formula.mastery_band(0.80), "mastered")

    def test_repeated_passes_reach_mastered_without_overflow(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        last = 0.20
        for i in range(20):
            out = _record(
                session, user, journey, problem_id=f"PY-C1-P{i}",
                passed=True, execution_status="PASSED",
                diagnosed_misconception_id=None, diagnostic_confidence=None,
                evidence_refs=["code"],
            )
            last = out["transition"]["new_mastery"]
            self.assertGreaterEqual(last, 0.0)
            self.assertLessEqual(last, 1.0)
        self.assertGreaterEqual(last, 0.80)
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["band"], "mastered")

    def test_repeated_fails_floor_at_zero(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        last = 0.20
        for i in range(20):
            out = _record(
                session, user, journey, problem_id=f"PY-C1-F{i}",
                execution_status="TIMEOUT",
                evidence_refs=["execution_status", "code"],
            )
            last = out["transition"]["new_mastery"]
            self.assertGreaterEqual(last, 0.0)
            self.assertLessEqual(last, 1.0)
        self.assertEqual(last, 0.0)


class HintDependenceTests(unittest.TestCase):
    def test_hint_reduces_pass_gain(self):
        s1 = _fresh_session(self)
        u1, j1 = _user_journey(s1)
        plain = _record(
            s1, u1, j1, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            hint_used=False, evidence_refs=["code"],
        )["transition"]
        s2 = _fresh_session(self)
        u2, j2 = _user_journey(s2)
        hinted = _record(
            s2, u2, j2, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            hint_used=True, evidence_refs=["code"],
        )["transition"]
        self.assertLess(hinted["new_mastery"], plain["new_mastery"])

    def test_hint_count_and_dependence_rate(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            hint_used=True, evidence_refs=["code"],
        )
        _record(
            session, user, journey, problem_id="PY-C1-002",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            hint_used=False, evidence_refs=["code"],
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["hint_count"], 1)
        self.assertAlmostEqual(view["hint_dependence"], 0.5)


class TransferSuccessTests(unittest.TestCase):
    def test_transfer_pass_bonus(self):
        s1 = _fresh_session(self)
        u1, j1 = _user_journey(s1)
        canon = _record(
            s1, u1, j1, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            variant_role="canonical", evidence_refs=["code"],
        )["transition"]
        s2 = _fresh_session(self)
        u2, j2 = _user_journey(s2)
        transfer = _record(
            s2, u2, j2, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            variant_role="transfer", evidence_refs=["code"],
        )["transition"]
        self.assertGreater(transfer["new_mastery"], canon["new_mastery"])

    def test_transfer_counts_and_rate(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            variant_role="transfer", evidence_refs=["code"],
        )
        _record(
            session, user, journey, problem_id="PY-C1-002",
            passed=False, execution_status="FAILED",
            diagnosed_misconception_id="C1-M01",
            variant_role="transfer", evidence_refs=["code"],
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["transfer_attempts"], 2)
        self.assertEqual(view["transfer_successes"], 1)
        self.assertAlmostEqual(view["transfer_success_rate"], 0.5)


class ImprovementDetectionTests(unittest.TestCase):
    def test_three_clean_passes_resolve_recurring(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(session, user, journey, problem_id="PY-C1-002")
        before = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertTrue(before["is_recurring"])
        improved = None
        for i in range(3):
            improved = _record(
                session, user, journey, problem_id=f"PY-C1-G{i}",
                passed=True, execution_status="PASSED",
                diagnosed_misconception_id=None, diagnostic_confidence=None,
                evidence_refs=["code"],
            )
        self.assertIn("C1-M01", improved["improved_ids"])
        after = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertTrue(after["is_improving"])
        self.assertFalse(after["active"])
        self.assertFalse(after["is_recurring"])
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertNotIn("C1-M01", view["active_misconception_ids"])

    def test_two_passes_not_enough(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(session, user, journey, problem_id="PY-C1-002")
        for i in range(2):
            out = _record(
                session, user, journey, problem_id=f"PY-C1-G{i}",
                passed=True, execution_status="PASSED",
                diagnosed_misconception_id=None, diagnostic_confidence=None,
                evidence_refs=["code"],
            )
        self.assertEqual(out["improved_ids"], [])
        mid = learner_engine.get_misconception_view(session, journey.id, "C1", "C1-M01")
        self.assertFalse(mid["is_improving"])

    def test_recurrence_blocks_improvement(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(
            session, user, journey, problem_id="PY-C1-G0",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        _record(
            session, user, journey, problem_id="PY-C1-G1",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        out = _record(session, user, journey, problem_id="PY-C1-003")
        self.assertEqual(out["improved_ids"], [])


class DeterminismTests(unittest.TestCase):
    def test_pure_formula_deterministic(self):
        args = (0.42, False, "RUNTIME_ERROR", True, False, 0.6)
        self.assertEqual(
            mastery_formula.compute_mastery_update(*args),
            mastery_formula.compute_mastery_update(*args),
        )

    def test_same_sequence_same_trajectory(self):
        def run():
            from sqlalchemy.orm import Session as _S  # noqa: F401 (keep import local)
            engine = get_engine("sqlite:///:memory:")
            init_db(engine)
            factory = get_session_factory(engine)
            session = factory()
            try:
                user = repositories.create_user(session)
                journey = repositories.create_journey(session, user.id, "python")
                steps = [
                    {"problem_id": "PY-C1-001", "passed": False,
                     "execution_status": "FAILED",
                     "diagnosed_misconception_id": "C1-M01",
                     "diagnostic_confidence": 0.7,
                     "evidence_refs": ["failed_test:P1"]},
                    {"problem_id": "PY-C1-002", "passed": True,
                     "execution_status": "PASSED",
                     "diagnosed_misconception_id": None,
                     "diagnostic_confidence": None,
                     "evidence_refs": ["code"]},
                ]
                deltas = []
                for step in steps:
                    out = learner_engine.record_attempt(
                        session, user_id=user.id, journey_id=journey.id,
                        concept_id="C1", isomorphic_group_id="ISO-C1-GRP",
                        variant_role="canonical", hint_used=False,
                        **step,
                    )
                    t = out["transition"]
                    deltas.append((t["previous_mastery"], t["new_mastery"],
                                   t["delta"], t["reason"]))
                return deltas
            finally:
                session.close()

        self.assertEqual(run(), run())


class TransitionHistoryTests(unittest.TestCase):
    def test_transitions_append_only_and_explainable(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(
            session, user, journey, problem_id="PY-C1-002",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        explained = learner_engine.explain_mastery(session, journey.id, "C1")
        self.assertEqual(len(explained["transitions"]), 2)
        first, second = explained["transitions"]
        self.assertLess(first["previous_mastery"], second["new_mastery"] + 1.0)
        self.assertIn("mastery", explained["narrative"].lower())
        self.assertIn(str(round(explained["concept_view"]["mastery"], 2)),
                      explained["narrative"])
        # Append-only: events ordered by id.
        events = repositories.list_events_for_journey(session, journey.id, concept_id="C1")
        ids = [e.id for e in events]
        self.assertEqual(ids, sorted(ids))
        kinds = {e.event_type for e in events}
        self.assertIn("attempt", kinds)
        self.assertIn("diagnosis", kinds)
        self.assertIn("mastery_transition", kinds)

    def test_snapshot_feeds_evidence_builder(self):
        from packages.evidence.builder import build_evidence_pack
        from packages.problem_schema.examples import EXAMPLE_PYTHON_PROBLEM

        session = _fresh_session(self)
        user, journey = _user_journey(session, track="python")
        learner_engine.record_attempt(
            session, user_id=user.id, journey_id=journey.id, concept_id="C3",
            problem_id="PY-C3-001", isomorphic_group_id="ISO-C3-SUM-EVENS",
            variant_role="canonical", passed=False, execution_status="FAILED",
            diagnosed_misconception_id="C3-M01", diagnostic_confidence=0.7,
            evidence_refs=["failed_test:P1"],
        )
        snapshot = learner_engine.snapshot_for_evidence(
            session, user.id, journey.id, "C3"
        )
        self.assertEqual(snapshot.language_track, "python")
        self.assertIsNotNone(snapshot.concept_state)
        exec_result = {
            "status": "FAILED", "language": "python", "execution_time_ms": 50,
            "stdout": "WRONG\n", "stderr": "",
            "tests": [{
                "test_id": "P1", "passed": False, "input": "5",
                "expected_output": "6", "actual_output": "WRONG\n",
                "stdout": "WRONG\n", "stderr": "",
                "exit_code": 0, "timed_out": False, "time_ms": 50,
            }],
            "passed_count": 0, "failed_count": 1, "failed_test_id": "P1",
            "expected_output": "6", "actual_output": "WRONG\n",
        }
        pack = build_evidence_pack(
            code="print('x')\n", problem=EXAMPLE_PYTHON_PROBLEM,
            execution_result=exec_result, learner_snapshot=snapshot,
        )
        self.assertEqual(pack.concept_id, "C3")
        self.assertIsNotNone(pack.concept_history)

    def test_trend_evolution(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        _record(
            session, user, journey, problem_id="PY-C1-002",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["trend"], "improving")
        _record(session, user, journey, problem_id="PY-C1-003")
        _record(session, user, journey, problem_id="PY-C1-004")
        _record(session, user, journey, problem_id="PY-C1-005")
        view2 = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view2["trend"], "declining")


class OwnershipAndSafetyTests(unittest.TestCase):
    def test_ai_service_never_writes_learner_state(self):
        import ast

        app_dir = _ROOT / "services" / "ai-service" / "app"
        for path in sorted(app_dir.glob("*.py")):
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=path.name)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    joined = " ".join(mods).lower()
                    self.assertNotIn("learner_engine", joined,
                                     f"{path.name}: AI service must not import learner engine")
                    self.assertNotIn("sqlalchemy", joined,
                                     f"{path.name}: AI service must not touch the DB")

    def test_engine_owns_mutations_via_repositories(self):
        import inspect

        src = inspect.getsource(learner_engine)
        self.assertIn("repositories", src)
        self.assertIn("update_concept_state", src)
        self.assertIn("increment_counter", src)
        self.assertIn("set_recurring_flag", src)
        self.assertIn("create_event", src)

    def test_no_hard_coded_secrets(self):
        for path in [
            _ROOT / "packages" / "mastery" / "formula.py",
            _ROOT / "packages" / "mastery" / "weakness.py",
            _SERVICE_DIR / "app" / "learner_engine.py",
        ]:
            src = path.read_text(encoding="utf-8")
            lowered = src.lower()
            for token in ("sk-", "sk-proj-", "api_key =", "password ="):
                self.assertNotIn(token, lowered, f"{path.name}: no secrets")
            self.assertNotIn("DATABASE_URL =", src)

    def test_rejects_bad_inputs(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        with self.assertRaises(ValueError):  # unknown concept
            _record(session, user, journey, concept_id="C9")
        with self.assertRaises(ValueError):  # misconception of another concept
            _record(session, user, journey, diagnosed_misconception_id="C2-M01")
        with self.assertRaises(ValueError):  # passed/status mismatch
            _record(session, user, journey, passed=True, execution_status="FAILED")
        with self.assertRaises(ValueError):  # bad variant role
            _record(session, user, journey, variant_role="boss-level")


if __name__ == "__main__":
    unittest.main()
