"""Step 18: richer adaptive inputs (packages.adaptive).

Verifies that enriched learner evidence flows into the deterministic
policy without changing R1..R8 decisions:

- ConceptState carries optional pass/fail + transfer + recent-rate evidence
  (defaults keep legacy constructors working).
- from_learner_view picks up Step 18 view keys, tolerates legacy views.
- to_dict / from_dict round-trip the new fields.
- supporting_evidence is richer; action selection stays deterministic.
- MisconceptionState carries distinct_variant_count (R3 evidence).
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
    ConceptState,
    MisconceptionState,
    recommend_next_actions,
)


def _state(**overrides):
    kwargs = {
        "concept_id": "C5",
        "mastery": 0.42,
        "mastery_band": "emerging",
        "trend": "stable",
        "attempt_count": 5,
        "hint_dependence": 0.1,
        "transfer_success_rate": 0.0,
    }
    kwargs.update(overrides)
    return ConceptState(**kwargs)


class BackwardsCompatTests(unittest.TestCase):
    def test_legacy_constructor_defaults(self):
        s = _state()
        self.assertEqual(s.pass_count, 0)
        self.assertEqual(s.fail_count, 0)
        self.assertEqual(s.transfer_attempts, 0)
        self.assertEqual(s.transfer_successes, 0)
        self.assertEqual(s.recent_pass_rate, 0.0)

    def test_legacy_view_without_new_keys(self):
        view = {
            "concept_id": "C5", "mastery": 0.42, "band": "emerging",
            "trend": "stable", "attempt_count": 5, "hint_dependence": 0.1,
            "transfer_success_rate": 0.0,
        }
        s = ConceptState.from_learner_view(view)
        self.assertEqual(s.attempt_count, 5)
        self.assertEqual(s.pass_count, 0)

    def test_round_trip(self):
        s = _state(pass_count=3, fail_count=2, transfer_attempts=2,
                   transfer_successes=1, recent_pass_rate=0.6)
        clone = ConceptState.from_dict(s.to_dict())
        self.assertEqual(clone, s)

    def test_invalid_transfer_counts_rejected(self):
        with self.assertRaises(ValueError):
            _state(transfer_attempts=1, transfer_successes=2)


class RicherEvidenceTests(unittest.TestCase):
    def test_from_enriched_learner_view(self):
        view = {
            "concept_id": "C5", "mastery": 0.70, "band": "proficient",
            "trend": "stable", "attempt_count": 6, "pass_count": 4,
            "fail_count": 2, "hint_dependence": 0.1,
            "transfer_success_rate": 0.5, "transfer_attempts": 2,
            "transfer_successes": 1,
            "recent_performance": {"last_5": [True, False, True, True, True],
                                   "pass_rate": 0.8},
        }
        s = ConceptState.from_learner_view(view)
        self.assertEqual(s.pass_count, 4)
        self.assertEqual(s.fail_count, 2)
        self.assertEqual(s.transfer_attempts, 2)
        self.assertAlmostEqual(s.recent_pass_rate, 0.8)

    def test_evidence_carries_richer_inputs(self):
        s = _state(pass_count=3, fail_count=2, transfer_attempts=2,
                   transfer_successes=1, recent_pass_rate=0.6)
        recs = recommend_next_actions([s], [], [], [])
        self.assertGreater(len(recs), 0)
        for rec in recs:
            ev = rec.supporting_evidence
            for key in ("pass_count", "fail_count", "transfer_attempts",
                        "transfer_successes", "recent_pass_rate"):
                self.assertIn(key, ev)

    def test_decisions_unchanged_by_enrichment(self):
        # Same core inputs with and without enrichment rank identically
        # (action types + reason codes + problem choice unchanged).
        from packages.adaptive import CurriculumInfo, ProblemInfo

        lean = _state()
        rich = _state(pass_count=3, fail_count=2, transfer_attempts=0,
                      transfer_successes=0, recent_pass_rate=0.6)
        curr = [CurriculumInfo.from_taxonomy("C5")]
        probs = [ProblemInfo(problem_id="PY-C5-001", concept_id="C5",
                             difficulty=2, isomorphic_group_id="ISO-C5-X",
                             variant_role="canonical")]
        recs_lean = recommend_next_actions([lean], [], curr, probs)
        recs_rich = recommend_next_actions([rich], [], curr, probs)
        self.assertEqual(
            [(r.action_type, r.reason_code, r.problem_id) for r in recs_lean],
            [(r.action_type, r.reason_code, r.problem_id) for r in recs_rich],
        )


class MisconceptionVariantEvidenceTests(unittest.TestCase):
    def test_variant_count_defaults_and_maps(self):
        m = MisconceptionState(
            misconception_id="C5-M02", concept_id="C5",
            occurrence_count=4, recent_count=3, is_recurring=True,
        )
        self.assertEqual(m.distinct_variant_count, 0)
        view = {
            "misconception_id": "C5-M02", "concept_id": "C5",
            "occurrence_count": 4, "recent_count": 3, "is_recurring": True,
            "distinct_variant_count": 2,
        }
        m2 = MisconceptionState.from_misconception_view(view)
        self.assertEqual(m2.distinct_variant_count, 2)
        self.assertEqual(
            MisconceptionState.from_dict(m2.to_dict()), m2
        )

    def test_recurring_evidence_includes_variants(self):
        s = _state(mastery=0.30, attempt_count=5)
        m = MisconceptionState(
            misconception_id="C5-M02", concept_id="C5",
            occurrence_count=4, recent_count=3, is_recurring=True,
            distinct_variant_count=2,
        )
        recs = recommend_next_actions([s], [m], [], [])
        review = next(
            r for r in recs if r.action_type.value == "REVIEW_CONCEPT"
        )
        self.assertEqual(review.supporting_evidence["distinct_variant_count"], 2)


if __name__ == "__main__":
    unittest.main()
