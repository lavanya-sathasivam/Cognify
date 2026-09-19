"""Unit tests for Step 9: Adaptive Engine / Roadmap Ranking.

Pure, deterministic, stdlib + unittest only. No DB, no LLM, no network.

Run from repo root:
    python -m unittest discover -s packages/adaptive/tests -t . -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.adaptive import (
    ActionType,
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    ProblemInfo,
    ReasonCode,
    recommend_next_actions,
)
from packages.adaptive import policy as policy_module
from packages.adaptive import ranking as ranking_module


def _state(concept_id="C5", mastery=0.42, band=None, trend="stable",
           attempts=5, hint=0.1, transfer=0.0, track=None):
    if band is None:
        band = "novice" if mastery < 0.40 else ("emerging" if mastery < 0.60 else ("proficient" if mastery < 0.80 else "mastered"))
    return ConceptState(
        concept_id=concept_id, mastery=mastery, mastery_band=band,
        trend=trend, attempt_count=attempts, hint_dependence=hint,
        transfer_success_rate=transfer, language_track=track,
    )


def _misc(mid="C5-M02", concept="C5", occ=4, recent=3, recurring=True):
    return MisconceptionState(
        misconception_id=mid, concept_id=concept,
        occurrence_count=occ, recent_count=recent, is_recurring=recurring,
    )


def _curr(concept_id, prereqs=(), threshold=0.60):
    return CurriculumInfo(concept_id=concept_id, prerequisites=prereqs, mastery_threshold=threshold)


def _tax_curr(concept_id, threshold=0.60):
    return CurriculumInfo.from_taxonomy(concept_id, mastery_threshold=threshold)


def _prob(pid="PY-C5-001", concept="C5", diff=2, group="ISO-C5-X", role="canonical"):
    return ProblemInfo(problem_id=pid, concept_id=concept, difficulty=diff,
                       isomorphic_group_id=group, variant_role=role)


def _types(recs):
    return [r.action_type for r in recs]


class PrerequisiteGateTests(unittest.TestCase):
    def test_prereq_not_mastered_ranked_first(self):
        # C5 requires C1,C3,C4 (taxonomy). C4 is weak.
        s_c5 = _state("C5", mastery=0.70, attempts=6)
        s_c4 = _state("C4", mastery=0.30, attempts=4)
        s_c1 = _state("C1", mastery=0.85, attempts=8)
        s_c3 = _state("C3", mastery=0.80, attempts=8)
        curricula = [_tax_curr(c) for c in ("C1", "C3", "C4", "C5")]
        recs = recommend_next_actions([s_c5, s_c4, s_c1, s_c3], [], curricula, [])
        self.assertGreater(len(recs), 0)
        first = recs[0]
        self.assertEqual(first.action_type, ActionType.REVIEW_PREREQUISITE)
        self.assertEqual(first.concept_id, "C4")
        self.assertEqual(first.reason_code, ReasonCode.PREREQUISITE_NOT_MASTERED)
        # Downstream harder actions suppressed while blocked.
        c5_actions = [r for r in recs if r.concept_id == "C5"]
        self.assertNotIn(ActionType.CHALLENGE_PROBLEM, [r.action_type for r in c5_actions])
        self.assertNotIn(ActionType.TRANSFER_PROBLEM, [r.action_type for r in c5_actions])

    def test_prereq_satisfied_no_gate(self):
        s_c5 = _state("C5", mastery=0.70, attempts=6)
        s_c4 = _state("C4", mastery=0.75, attempts=6)
        s_c1 = _state("C1", mastery=0.85, attempts=8)
        s_c3 = _state("C3", mastery=0.80, attempts=8)
        curricula = [_tax_curr(c) for c in ("C1", "C3", "C4", "C5")]
        recs = recommend_next_actions([s_c5, s_c4, s_c1, s_c3], [], curricula, [])
        self.assertNotIn(ActionType.REVIEW_PREREQUISITE, _types(recs))


class VeryLowMasteryTests(unittest.TestCase):
    def test_below_point_four_zero_review_plus_remedial(self):
        s = _state("C1", mastery=0.25, attempts=3)
        recs = recommend_next_actions([s], [], [_curr("C1")], [_prob("PY-C1-001", "C1")])
        types = _types(recs)
        self.assertIn(ActionType.REVIEW_CONCEPT, types)
        self.assertIn(ActionType.REMEDIAL_PROBLEM, types)
        self.assertNotIn(ActionType.CHALLENGE_PROBLEM, types)


class RecurringTests(unittest.TestCase):
    def test_recurring_boosts_priority_and_mentions_weakness(self):
        s = _state("C5", mastery=0.30, attempts=5)
        rec_misc = _misc(recurring=True)
        non_misc = _misc(recurring=False)
        recs_rec = recommend_next_actions([s], [rec_misc], [_curr("C5")], [_prob()])
        recs_non = recommend_next_actions([s], [non_misc], [_curr("C5")], [_prob()])
        prio_rec = next(r.priority for r in recs_rec if r.action_type == ActionType.REVIEW_CONCEPT)
        prio_non = next(r.priority for r in recs_non if r.action_type == ActionType.REVIEW_CONCEPT)
        self.assertGreater(prio_rec, prio_non)
        review = next(r for r in recs_rec if r.action_type == ActionType.REVIEW_CONCEPT)
        self.assertEqual(review.reason_code, ReasonCode.RECURRING_MISCONCEPTION)
        self.assertIn("recurring weakness", review.reason.lower())
        self.assertEqual(review.misconception_id, "C5-M02")
        remedial = next(r for r in recs_rec if r.action_type == ActionType.REMEDIAL_PROBLEM)
        self.assertEqual(remedial.reason_code, ReasonCode.RECURRING_MISCONCEPTION)


class EmergingTests(unittest.TestCase):
    def test_emerging_yields_practice_no_challenge(self):
        for mastery in (0.40, 0.42, 0.59):
            with self.subTest(mastery=mastery):
                s = _state("C5", mastery=mastery, attempts=5)
                recs = recommend_next_actions([s], [], [_curr("C5")], [_prob()])
                types = _types(recs)
                self.assertIn(ActionType.PRACTICE_PROBLEM, types)
                self.assertNotIn(ActionType.CHALLENGE_PROBLEM, types)


class ProficientTests(unittest.TestCase):
    def test_proficient_practice_and_transfer_when_ready(self):
        s = _state("C5", mastery=0.70, attempts=6, transfer=0.8)
        probs = [_prob("PY-C5-001", "C5", 2, "ISO-C5-X", "canonical"),
                 _prob("PY-C5-010", "C5", 2, "ISO-C5-Y", "transfer")]
        recs = recommend_next_actions([s], [], [_curr("C5")], probs)
        types = _types(recs)
        self.assertIn(ActionType.PRACTICE_PROBLEM, types)
        self.assertIn(ActionType.TRANSFER_PROBLEM, types)
        transfer = next(r for r in recs if r.action_type == ActionType.TRANSFER_PROBLEM)
        self.assertEqual(transfer.reason_code, ReasonCode.READY_FOR_TRANSFER)
        self.assertEqual(transfer.problem_id, "PY-C5-010")

    def test_proficient_no_transfer_without_evidence(self):
        s = _state("C5", mastery=0.70, attempts=0)
        recs = recommend_next_actions([s], [], [_curr("C5")], [_prob()])
        self.assertNotIn(ActionType.TRANSFER_PROBLEM, _types(recs))
        self.assertIn(ActionType.PRACTICE_PROBLEM, _types(recs))


class MasteredTests(unittest.TestCase):
    def test_mastered_yields_challenge(self):
        s = _state("C5", mastery=0.85, attempts=8, transfer=0.7)
        probs = [_prob("PY-C5-001", "C5", 2, "ISO-C5-X", "canonical"),
                 _prob("PY-C5-009", "C5", 5, "ISO-C5-Z", "canonical"),
                 _prob("PY-C5-010", "C5", 3, "ISO-C5-Y", "transfer")]
        recs = recommend_next_actions([s], [], [_curr("C5")], probs)
        types = _types(recs)
        self.assertIn(ActionType.CHALLENGE_PROBLEM, types)
        ch = next(r for r in recs if r.action_type == ActionType.CHALLENGE_PROBLEM)
        self.assertEqual(ch.reason_code, ReasonCode.READY_FOR_CHALLENGE)


class DecliningTrendTests(unittest.TestCase):
    def test_declining_increases_review_priority(self):
        s_stable = _state("C5", mastery=0.50, trend="stable", attempts=5)
        s_decl = _state("C5", mastery=0.50, trend="declining", attempts=5)
        recs_stable = recommend_next_actions([s_stable], [], [_curr("C5")], [])
        recs_decl = recommend_next_actions([s_decl], [], [_curr("C5")], [])
        prio_stable = next(r.priority for r in recs_stable if r.action_type == ActionType.PRACTICE_PROBLEM)
        prio_decl = next(r.priority for r in recs_decl if r.action_type == ActionType.PRACTICE_PROBLEM)
        self.assertGreater(prio_decl, prio_stable)


class HintDependenceTests(unittest.TestCase):
    def test_high_hint_suppresses_challenge_prefers_review(self):
        s_clean = _state("C5", mastery=0.85, attempts=8, hint=0.1)
        s_hint = _state("C5", mastery=0.85, attempts=8, hint=0.8)
        recs_clean = recommend_next_actions([s_clean], [], [_curr("C5")], [_prob()])
        recs_hint = recommend_next_actions([s_hint], [], [_curr("C5")], [_prob()])
        self.assertIn(ActionType.CHALLENGE_PROBLEM, _types(recs_clean))
        self.assertNotIn(ActionType.CHALLENGE_PROBLEM, _types(recs_hint))
        self.assertNotIn(ActionType.TRANSFER_PROBLEM, _types(recs_hint))
        self.assertIn(ActionType.REVIEW_CONCEPT, _types(recs_hint))


class DeterminismTests(unittest.TestCase):
    def _sample(self):
        s1 = _state("C5", mastery=0.42, attempts=5)
        s2 = _state("C4", mastery=0.70, attempts=6)
        m = _misc()
        curricula = [_tax_curr("C4"), _tax_curr("C5")]
        probs = [_prob("PY-C5-002", "C5", 2, "ISO-C5-X", "canonical"),
                 _prob("PY-C5-001", "C5", 2, "ISO-C5-X", "canonical")]
        return s1, s2, m, curricula, probs

    def test_same_input_same_output(self):
        s1, s2, m, curricula, probs = self._sample()
        first = recommend_next_actions([s1, s2], [m], curricula, probs)
        second = recommend_next_actions([s1, s2], [m], curricula, probs)
        self.assertEqual([r.to_dict() for r in first], [r.to_dict() for r in second])

    def test_problem_order_does_not_matter(self):
        s1, s2, m, curricula, probs = self._sample()
        forward = recommend_next_actions([s1, s2], [m], curricula, probs)
        backward = recommend_next_actions([s1, s2], [m], curricula, list(reversed(probs)))
        self.assertEqual([r.to_dict() for r in forward], [r.to_dict() for r in backward])


class MultiConceptTests(unittest.TestCase):
    def test_weaker_concept_ranked_first(self):
        weak = _state("C1", mastery=0.20, attempts=3)
        strong = _state("C2", mastery=0.75, attempts=6)
        curricula = [_curr("C1"), _curr("C2", prereqs=())]
        recs = recommend_next_actions([weak, strong], [], curricula, [])
        first_c1 = next(i for i, r in enumerate(recs) if r.concept_id == "C1")
        first_c2 = next(i for i, r in enumerate(recs) if r.concept_id == "C2")
        self.assertLess(first_c1, first_c2)


class LanguageIsolationTests(unittest.TestCase):
    def test_track_scoped_and_mismatch_rejected(self):
        s_py = _state("C5", mastery=0.42, attempts=5, track="python")
        s_java = _state("C5", mastery=0.42, attempts=5, track="java")
        m = _misc()
        curricula = [_curr("C5")]
        probs = [_prob()]
        recs_py = recommend_next_actions([s_py], [m], curricula, probs, language_track="python")
        recs_java = recommend_next_actions([s_java], [m], curricula, probs, language_track="java")
        self.assertEqual([r.action_type for r in recs_py], [r.action_type for r in recs_java])
        for r in recs_py:
            self.assertEqual(r.supporting_evidence.get("language_track"), "python")
        for r in recs_java:
            self.assertEqual(r.supporting_evidence.get("language_track"), "java")
        with self.assertRaises(ValueError):
            recommend_next_actions([s_py], [m], curricula, probs, language_track="java")


class ExplainabilityTests(unittest.TestCase):
    def test_every_rec_has_code_and_evidence(self):
        s = _state("C5", mastery=0.42, attempts=5)
        m = _misc()
        recs = recommend_next_actions([s], [m], [_curr("C5")], [_prob()])
        self.assertGreater(len(recs), 0)
        for r in recs:
            with self.subTest(action=r.action_type.value):
                self.assertIsInstance(r.reason_code, ReasonCode)
                self.assertGreaterEqual(len(r.reason.strip()), 10)
                self.assertLessEqual(len(r.reason.strip()), 500)
                self.assertIsInstance(r.supporting_evidence, dict)
                self.assertIn("mastery", r.supporting_evidence)
                self.assertIn("mastery_threshold", r.supporting_evidence)

    def test_step8_view_adapter(self):
        view = {"concept_id": "C5", "mastery": 0.42, "band": "emerging",
                "trend": "stable", "attempt_count": 5, "hint_dependence": 0.1,
                "transfer_success_rate": 0.0, "language_track": "python",
                "pass_count": 2, "extra": "ignored"}
        mview = {"misconception_id": "C5-M02", "concept_id": "C5",
                 "occurrence_count": 4, "recent_count": 3, "is_recurring": True,
                 "last_seen_at": None, "active": True}
        from packages.adaptive import ConceptState as CS, MisconceptionState as MS
        s = CS.from_learner_view(view)
        m = MS.from_misconception_view(mview)
        recs = recommend_next_actions([s], [m], [_tax_curr("C5")], [_prob()])
        self.assertGreater(len(recs), 0)


class SafetyTests(unittest.TestCase):
    def test_no_db_llm_or_mastery_calc(self):
        import ast

        adaptive_dir = _ROOT / "packages" / "adaptive"
        for path in sorted(adaptive_dir.glob("*.py")):
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=path.name)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                            else [node.module or ""])
                    joined = " ".join(mods).lower()
                    for forbidden in ("sqlalchemy", "openai", "anthropic", "httpx",
                                      "requests", "sklearn", "torch", "subprocess"):
                        self.assertNotIn(forbidden, joined, f"{path.name}: forbidden import")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in {"eval", "exec", "compile"}:
                    self.fail(f"{path.name}: forbidden call")
        import inspect
        for mod in (policy_module, ranking_module):
            src = inspect.getsource(mod)
            self.assertNotIn("compute_mastery_update", src)
            self.assertNotIn("complete(", src)

    def test_models_are_strict(self):
        with self.assertRaises(ValueError):
            _state("C9", mastery=0.5)
        with self.assertRaises(ValueError):
            _state("C5", mastery=1.5)
        with self.assertRaises(ValueError):
            MisconceptionState(misconception_id="C2-M01", concept_id="C5",
                               occurrence_count=1, recent_count=0, is_recurring=False)


if __name__ == "__main__":
    unittest.main()
