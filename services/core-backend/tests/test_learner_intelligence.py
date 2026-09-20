"""Step 18: learner-intelligence upgrade tests (core-backend).

Covers the concrete gaps fixed in Step 18 without duplicating Step 8
coverage:

- structured transfer tracking (canonical vs transfer, failures, breakdown)
- recent attempt history in the concept view
- read-view rate safety on inconsistent counters (never crash)
- enriched mastery-transition explanations (previous/current/reason/attempt)
- misconception supporting evidence (problem ids / groups)
- empty/small-history trend safety, mastery bounds
- mastery package public exports
- adaptive-engine compatibility with enriched views

Run from repo root:
    python -m pytest services/core-backend/tests/test_learner_intelligence.py -q
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
        "evidence_refs": ["failed_test:P1"],
        "is_transfer": None,
    }
    kwargs.update(overrides)
    return learner_engine.record_attempt(session, **kwargs)


class TransferBreakdownTests(unittest.TestCase):
    def test_canonical_only_breakdown(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["transfer_attempts"], 0)
        self.assertEqual(view["transfer_successes"], 0)
        self.assertEqual(view["transfer_failures"], 0)
        self.assertEqual(view["canonical_attempts"], 1)
        self.assertEqual(
            view["transfer_breakdown"],
            {"attempts": 0, "successes": 0, "failures": 0, "success_rate": 0.0},
        )
        self.assertEqual(view["transfer_success_rate"], 0.0)

    def test_mixed_canonical_and_transfer(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            variant_role="canonical", evidence_refs=["code"],
        )
        _record(
            session, user, journey, problem_id="PY-C1-T1",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            variant_role="transfer", evidence_refs=["code"],
        )
        _record(
            session, user, journey, problem_id="PY-C1-T2",
            passed=False, execution_status="FAILED",
            diagnosed_misconception_id="C1-M01",
            variant_role="transfer", evidence_refs=["code"],
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["attempt_count"], 3)
        self.assertEqual(view["transfer_attempts"], 2)
        self.assertEqual(view["transfer_successes"], 1)
        self.assertEqual(view["transfer_failures"], 1)
        self.assertEqual(view["canonical_attempts"], 1)
        self.assertEqual(view["transfer_breakdown"]["failures"], 1)
        self.assertAlmostEqual(view["transfer_breakdown"]["success_rate"], 0.5)
        # Consistency: canonical + transfer == total; successes + failures == attempts.
        self.assertEqual(
            view["canonical_attempts"] + view["transfer_attempts"],
            view["attempt_count"],
        )
        self.assertEqual(
            view["transfer_breakdown"]["successes"]
            + view["transfer_breakdown"]["failures"],
            view["transfer_breakdown"]["attempts"],
        )

    def test_new_learner_breakdown_zeros(self):
        session = _fresh_session(self)
        _user, journey = _user_journey(session)
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["transfer_failures"], 0)
        self.assertEqual(view["canonical_attempts"], 0)
        self.assertEqual(view["recent_history"], [])


class RecentHistoryTests(unittest.TestCase):
    def test_recent_history_tracks_attempt_evidence(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(
            session, user, journey, problem_id="PY-C1-T1",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            variant_role="transfer", hint_used=True, evidence_refs=["code"],
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        hist = view["recent_history"]
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0]["problem_id"], "PY-C1-001")
        self.assertFalse(hist[0]["passed"])
        self.assertFalse(hist[0]["is_transfer"])
        self.assertEqual(hist[1]["problem_id"], "PY-C1-T1")
        self.assertTrue(hist[1]["passed"])
        self.assertTrue(hist[1]["hint_used"])
        self.assertTrue(hist[1]["is_transfer"])
        # recent_performance still consistent with history.
        self.assertEqual(view["recent_performance"]["last_5"], [False, True])

    def test_repeated_attempts_accumulate(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        for i in range(4):
            _record(
                session, user, journey, problem_id=f"PY-C1-00{i}",
                passed=(i % 2 == 0),
                execution_status=("PASSED" if i % 2 == 0 else "FAILED"),
                diagnosed_misconception_id=(None if i % 2 == 0 else "C1-M01"),
                diagnostic_confidence=(None if i % 2 == 0 else 0.6),
                evidence_refs=["code"],
            )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view["attempt_count"], 4)
        self.assertEqual(view["pass_count"], 2)
        self.assertEqual(view["fail_count"], 2)
        self.assertEqual(len(view["recent_history"]), 4)


class SafeRateTests(unittest.TestCase):
    def test_inconsistent_counters_do_not_crash_view(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey)
        # Corrupt the row directly (repositories allow >= 0 but no cross-check).
        repositories.update_concept_state(
            session, journey.id, "C1", hint_count=10, attempt_count=2,
            transfer_attempts=1, transfer_successes=5,
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        # Clamped, never raises, always in [0, 1].
        self.assertEqual(view["hint_dependence"], 1.0)
        self.assertEqual(view["transfer_success_rate"], 1.0)
        self.assertGreaterEqual(view["hint_dependence"], 0.0)
        self.assertLessEqual(view["hint_dependence"], 1.0)

    def test_safe_helpers_never_raise(self):
        self.assertEqual(learner_engine._safe_hint_dependence(0, 0), 0.0)
        self.assertEqual(learner_engine._safe_hint_dependence(5, 2), 1.0)
        self.assertEqual(learner_engine._safe_transfer_rate(0, 0), 0.0)
        self.assertEqual(learner_engine._safe_transfer_rate(9, 3), 1.0)
        self.assertAlmostEqual(
            learner_engine._safe_hint_dependence(1, 4), 0.25
        )

    def test_strict_formula_still_rejects_bad_counts(self):
        # Write-path formula stays strict: over-counts raise.
        with self.assertRaises(ValueError):
            mastery_formula.hint_dependence_rate(5, 4)
        with self.assertRaises(ValueError):
            mastery_formula.transfer_success_rate(3, 2)


class ExplanationTests(unittest.TestCase):
    def test_trace_carries_full_transition_evidence(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(
            session, user, journey, problem_id="PY-C1-T1",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            variant_role="transfer", hint_used=True, evidence_refs=["code"],
        )
        explained = learner_engine.explain_mastery(session, journey.id, "C1")
        self.assertEqual(len(explained["transitions"]), 2)
        for entry in explained["transitions"]:
            for key in (
                "previous_mastery", "new_mastery", "delta", "reason",
                "evidence_refs", "attempt_number", "hint_used",
                "is_transfer", "band_before", "band_after", "trend",
                "passed", "execution_status", "problem_id",
                "isomorphic_group_id",
            ):
                self.assertIn(key, entry, f"trace missing {key}")
        first, second = explained["transitions"]
        self.assertEqual(first["attempt_number"], 1)
        self.assertEqual(second["attempt_number"], 2)
        self.assertFalse(first["is_transfer"])
        self.assertTrue(second["is_transfer"])
        self.assertTrue(second["hint_used"])
        # Narrative answers why: mastery, band, trend, hint, transfer, attempts.
        narrative = explained["narrative"].lower()
        for token in ("mastery", "trend", "hint", "transfer", "attempt"):
            self.assertIn(token, narrative)

    def test_empty_history_explanation(self):
        session = _fresh_session(self)
        _user, journey = _user_journey(session)
        explained = learner_engine.explain_mastery(session, journey.id, "C1")
        self.assertEqual(explained["transitions"], [])
        self.assertIn("no mastery transitions", explained["narrative"].lower())

    def test_transition_preserves_previous_current_reason(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        out = _record(session, user, journey)
        t = out["transition"]
        for key in (
            "previous_mastery", "new_mastery", "delta", "reason",
            "evidence_refs", "attempt_number", "band_before",
            "band_after", "trend",
        ):
            self.assertIn(key, t)
        self.assertEqual(t["attempt_number"], 1)
        self.assertLess(t["new_mastery"], t["previous_mastery"])


class MisconceptionEvidenceTests(unittest.TestCase):
    def test_supporting_problem_ids_back_recurrence(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(session, user, journey, problem_id="PY-C1-002")
        view = learner_engine.get_misconception_view(
            session, journey.id, "C1", "C1-M01"
        )
        self.assertEqual(view["occurrence_count"], 2)
        self.assertTrue(view["is_recurring"])
        self.assertEqual(
            view["supporting_problem_ids"], ["PY-C1-001", "PY-C1-002"]
        )
        self.assertIn("ISO-C1-GRP", view["supporting_groups"])

    def test_unseen_misconception_has_empty_evidence(self):
        session = _fresh_session(self)
        _user, journey = _user_journey(session)
        view = learner_engine.get_misconception_view(
            session, journey.id, "C1", "C1-M01"
        )
        self.assertEqual(view["supporting_problem_ids"], [])
        self.assertEqual(view["supporting_groups"], [])


class SmallHistoryAndBoundaryTests(unittest.TestCase):
    def test_empty_trend_unknown_single_stable(self):
        self.assertEqual(mastery_formula.compute_trend([]), "unknown")
        self.assertEqual(mastery_formula.compute_trend([True]), "stable")
        self.assertEqual(mastery_formula.compute_trend([False]), "stable")

    def test_two_same_outcomes_set_trend(self):
        self.assertEqual(mastery_formula.compute_trend([True, True]), "improving")
        self.assertEqual(mastery_formula.compute_trend([False, False]), "declining")

    def test_engine_trend_evolution_small_histories(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        view0 = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view0["trend"], "unknown")
        _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        view1 = learner_engine.get_concept_view(session, journey.id, "C1")
        self.assertEqual(view1["trend"], "stable")

    def test_mastery_stays_bounded(self):
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

    def test_empty_pass_rate_neutral_for_formula(self):
        self.assertEqual(mastery_formula.recent_pass_rate([]), 0.5)
        new, _, _ = mastery_formula.compute_mastery_update(
            0.20, True, "PASSED", False, False, 0.5
        )
        self.assertAlmostEqual(new, 0.32)


class MasteryExportTests(unittest.TestCase):
    def test_transfer_rate_and_normalize_exported(self):
        import packages.mastery as mastery_pkg

        self.assertTrue(hasattr(mastery_pkg, "transfer_success_rate"))
        self.assertTrue(hasattr(mastery_pkg, "normalize_execution_status"))
        self.assertIn("transfer_success_rate", mastery_pkg.__all__)
        self.assertIn("normalize_execution_status", mastery_pkg.__all__)
        self.assertEqual(mastery_pkg.transfer_success_rate(1, 2), 0.5)
        self.assertEqual(mastery_pkg.normalize_execution_status("passed"), "PASSED")


class AdaptiveCompatibilityTests(unittest.TestCase):
    def test_enriched_view_feeds_adaptive(self):
        from packages.adaptive import ConceptState, recommend_next_actions

        session = _fresh_session(self)
        user, journey = _user_journey(session)
        _record(session, user, journey, problem_id="PY-C1-001")
        _record(
            session, user, journey, problem_id="PY-C1-002",
            passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        view = learner_engine.get_concept_view(session, journey.id, "C1")
        state = ConceptState.from_learner_view(view)
        self.assertEqual(state.attempt_count, view["attempt_count"])
        self.assertEqual(state.pass_count, view["pass_count"])
        self.assertEqual(state.fail_count, view["fail_count"])
        self.assertEqual(state.transfer_attempts, view["transfer_attempts"])
        recs = recommend_next_actions(
            [state], [], [], [], language_track="python"
        )
        self.assertGreater(len(recs), 0)
        for rec in recs:
            self.assertIn("pass_count", rec.supporting_evidence)
            self.assertIn("transfer_attempts", rec.supporting_evidence)

    def test_single_pass_does_not_claim_mastered(self):
        session = _fresh_session(self)
        user, journey = _user_journey(session)
        out = _record(
            session, user, journey, passed=True, execution_status="PASSED",
            diagnosed_misconception_id=None, diagnostic_confidence=None,
            evidence_refs=["code"],
        )
        self.assertNotEqual(out["concept_view"]["band"], "mastered")
        self.assertAlmostEqual(out["transition"]["new_mastery"], 0.32)


if __name__ == "__main__":
    unittest.main()
