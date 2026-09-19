"""Unit tests for Step 8 pure mastery formula + weakness rules.

Stdlib + unittest only. No DB, no LLM, no I/O.

Run from repo root:
    python -m unittest discover -s packages/mastery/tests -t . -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.mastery import formula, weakness


class InitialAndBandTests(unittest.TestCase):
    def test_initial_mastery_is_point_two_zero(self):
        self.assertEqual(formula.INITIAL_MASTERY, 0.20)

    def test_bands(self):
        cases = [
            (0.0, "novice"),
            (0.20, "novice"),
            (0.39, "novice"),
            (0.3999, "novice"),
            (0.40, "emerging"),
            (0.50, "emerging"),
            (0.59, "emerging"),
            (0.60, "proficient"),
            (0.70, "proficient"),
            (0.79, "proficient"),
            (0.80, "mastered"),
            (0.95, "mastered"),
            (1.0, "mastered"),
        ]
        for score, band in cases:
            with self.subTest(score=score):
                self.assertEqual(formula.mastery_band(score), band)

    def test_band_rejects_out_of_range(self):
        for bad in (-0.1, 1.5, "0.5", True, None):
            with self.assertRaises((TypeError, ValueError), msg=repr(bad)):
                formula.mastery_band(bad)

    def test_clamp(self):
        self.assertEqual(formula.clamp_mastery(-5), 0.0)
        self.assertEqual(formula.clamp_mastery(2), 1.0)
        self.assertEqual(formula.clamp_mastery(0.62), 0.62)


class SeverityTests(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(formula.severity_for_status("PASSED"), 0.0)
        self.assertEqual(formula.severity_for_status("failed"), 0.5)
        self.assertEqual(formula.severity_for_status(" COMPILE_ERROR "), 0.75)
        self.assertEqual(formula.severity_for_status("runtime_error"), 0.75)
        self.assertEqual(formula.severity_for_status("TIMEOUT"), 1.0)

    def test_unknown_rejected(self):
        with self.assertRaises(ValueError):
            formula.severity_for_status("GUUESSED")


class MasteryUpdateTests(unittest.TestCase):
    def test_pass_independent_canonical_neutral(self):
        new, delta, reason = formula.compute_mastery_update(
            0.20, True, "PASSED", False, False, 0.5
        )
        self.assertAlmostEqual(new, 0.32)
        self.assertAlmostEqual(delta, 0.12)
        self.assertIn("pass", reason)

    def test_pass_with_hint_is_smaller_gain(self):
        plain = formula.compute_mastery_update(0.20, True, "PASSED", False, False, 0.5)
        hinted = formula.compute_mastery_update(0.20, True, "PASSED", True, False, 0.5)
        self.assertLess(hinted[0], plain[0])
        self.assertAlmostEqual(hinted[0], 0.26)  # 0.20 + 0.06

    def test_pass_transfer_bonus(self):
        canon = formula.compute_mastery_update(0.20, True, "PASSED", False, False, 0.5)
        transfer = formula.compute_mastery_update(0.20, True, "PASSED", False, True, 0.5)
        self.assertGreater(transfer[0], canon[0])
        self.assertAlmostEqual(transfer[0], 0.36)  # 0.20 + 0.16

    def test_fail_magnitudes_by_severity(self):
        failed = formula.compute_mastery_update(0.50, False, "FAILED", False, False, 0.5)
        timeout = formula.compute_mastery_update(0.50, False, "TIMEOUT", False, False, 0.5)
        compile_err = formula.compute_mastery_update(
            0.50, False, "COMPILE_ERROR", False, False, 0.5
        )
        self.assertLess(timeout[0], compile_err[0])
        self.assertLess(compile_err[0], failed[0])
        self.assertAlmostEqual(failed[0], 0.415)  # 0.50 - 0.085
        self.assertAlmostEqual(timeout[0], 0.38)  # 0.50 - 0.12

    def test_fail_with_hint_penalized_more(self):
        plain = formula.compute_mastery_update(0.50, False, "FAILED", False, False, 0.5)
        hinted = formula.compute_mastery_update(0.50, False, "FAILED", True, False, 0.5)
        self.assertLess(hinted[0], plain[0])

    def test_fail_transfer_penalized_more(self):
        canon = formula.compute_mastery_update(0.50, False, "FAILED", False, False, 0.5)
        transfer = formula.compute_mastery_update(0.50, False, "FAILED", False, True, 0.5)
        self.assertLess(transfer[0], canon[0])

    def test_recent_momentum(self):
        hot = formula.compute_mastery_update(0.50, True, "PASSED", False, False, 1.0)
        cold = formula.compute_mastery_update(0.50, True, "PASSED", False, False, 0.0)
        self.assertGreater(hot[0], cold[0])
        hot_fail = formula.compute_mastery_update(0.50, False, "FAILED", False, False, 1.0)
        cold_fail = formula.compute_mastery_update(0.50, False, "FAILED", False, False, 0.0)
        self.assertGreater(hot_fail[0], cold_fail[0])

    def test_deterministic(self):
        args = (0.62, False, "TIMEOUT", True, True, 0.75)
        first = formula.compute_mastery_update(*args)
        second = formula.compute_mastery_update(*args)
        self.assertEqual(first, second)

    def test_boundaries_clamped(self):
        new, delta, _ = formula.compute_mastery_update(0.99, True, "PASSED", False, True, 1.0)
        self.assertLessEqual(new, 1.0)
        new2, _, _ = formula.compute_mastery_update(0.01, False, "TIMEOUT", True, True, 0.0)
        self.assertGreaterEqual(new2, 0.0)
        # Saturating stays at bounds.
        top, _, _ = formula.compute_mastery_update(1.0, True, "PASSED", False, True, 1.0)
        self.assertEqual(top, 1.0)
        bottom, _, _ = formula.compute_mastery_update(0.0, False, "TIMEOUT", True, True, 0.0)
        self.assertEqual(bottom, 0.0)

    def test_passed_status_agreement_enforced(self):
        with self.assertRaises(ValueError):
            formula.compute_mastery_update(0.5, True, "FAILED", False, False, 0.5)
        with self.assertRaises(ValueError):
            formula.compute_mastery_update(0.5, False, "PASSED", False, False, 0.5)

    def test_invalid_inputs_rejected(self):
        with self.assertRaises((TypeError, ValueError)):
            formula.compute_mastery_update(1.5, True, "PASSED", False, False, 0.5)
        with self.assertRaises((TypeError, ValueError)):
            formula.compute_mastery_update(0.5, True, "PASSED", "no", False, 0.5)
        with self.assertRaises((TypeError, ValueError)):
            formula.compute_mastery_update(0.5, True, "PASSED", False, False, 2.0)


class TrendAndRateTests(unittest.TestCase):
    def test_trend(self):
        self.assertEqual(formula.compute_trend([]), "unknown")
        self.assertEqual(formula.compute_trend([True]), "stable")
        self.assertEqual(formula.compute_trend([False]), "stable")
        self.assertEqual(formula.compute_trend([True, True]), "improving")
        self.assertEqual(formula.compute_trend([False, False]), "declining")
        self.assertEqual(formula.compute_trend([True, False]), "stable")
        self.assertEqual(formula.compute_trend([True, True, True]), "improving")
        self.assertEqual(formula.compute_trend([False, False, False]), "declining")
        self.assertEqual(formula.compute_trend([True, False, True]), "stable")
        self.assertEqual(formula.compute_trend([True, True, False]), "stable")

    def test_recent_pass_rate(self):
        self.assertEqual(formula.recent_pass_rate([]), 0.5)
        self.assertEqual(formula.recent_pass_rate([True, True]), 1.0)
        self.assertEqual(formula.recent_pass_rate([True, False]), 0.5)
        self.assertEqual(formula.recent_pass_rate([False, False, False]), 0.0)
        # Window honored.
        self.assertEqual(
            formula.recent_pass_rate([False] * 10 + [True] * 5, window=5), 1.0
        )

    def test_hint_dependence(self):
        self.assertEqual(formula.hint_dependence_rate(0, 0), 0.0)
        self.assertEqual(formula.hint_dependence_rate(1, 4), 0.25)
        with self.assertRaises(ValueError):
            formula.hint_dependence_rate(5, 4)

    def test_transfer_rate(self):
        self.assertEqual(formula.transfer_success_rate(0, 0), 0.0)
        self.assertEqual(formula.transfer_success_rate(1, 2), 0.5)
        with self.assertRaises(ValueError):
            formula.transfer_success_rate(3, 2)

    def test_is_transfer_variant(self):
        self.assertTrue(formula.is_transfer_variant("transfer"))
        self.assertTrue(formula.is_transfer_variant(" Transfer "))
        self.assertFalse(formula.is_transfer_variant("canonical"))
        self.assertFalse(formula.is_transfer_variant("remedial"))


class WeaknessRuleTests(unittest.TestCase):
    def test_r1_recent(self):
        flag, reason = weakness.check_recurring(2, 2, 1)
        self.assertTrue(flag)
        self.assertIn("last 5", reason)

    def test_r2_historical(self):
        flag, reason = weakness.check_recurring(3, 1, 1)
        self.assertTrue(flag)
        self.assertIn("historical", reason)

    def test_r3_variants(self):
        flag, reason = weakness.check_recurring(2, 1, 2)
        self.assertTrue(flag)
        self.assertIn("variant", reason)

    def test_negative(self):
        flag, _ = weakness.check_recurring(1, 1, 1)
        self.assertFalse(flag)
        flag2, _ = weakness.check_recurring(0, 0, 0)
        self.assertFalse(flag2)

    def test_recent_count(self):
        hist = ["C1-M01", None, "c1-m01", "C1-M02", "C1-M01", "C1-M01"]
        self.assertEqual(weakness.recent_occurrence_count(hist, "C1-M01", window=5), 3)
        self.assertEqual(weakness.recent_occurrence_count(hist, "C1-M02", window=5), 1)
        self.assertEqual(weakness.recent_occurrence_count([], "C1-M01"), 0)

    def test_distinct_variants(self):
        self.assertEqual(weakness.distinct_variant_count(["P1", "P1", "P2"]), 2)
        self.assertEqual(weakness.distinct_variant_count(["", "  "]), 0)
        self.assertEqual(weakness.distinct_variant_count([]), 0)

    def test_isomorphic_variant_count_same_group(self):
        occ = [("PY-C1-001", "ISO-C1-SAME"), ("PY-C1-002", "ISO-C1-SAME")]
        self.assertEqual(weakness.isomorphic_variant_count(occ), 2)

    def test_isomorphic_variant_count_different_groups(self):
        occ = [("PY-C1-001", "ISO-C1-A"), ("PY-C1-002", "ISO-C1-B")]
        self.assertEqual(weakness.isomorphic_variant_count(occ), 1)

    def test_isomorphic_variant_count_dedupes_and_skips_empty(self):
        occ = [
            ("PY-C1-001", "ISO-C1-SAME"),
            ("PY-C1-001", "ISO-C1-SAME"),
            ("", "ISO-C1-SAME"),
            ("PY-C1-002", "  "),
            (None, "ISO-C1-SAME"),
            ("PY-C1-003", None),
        ]
        self.assertEqual(weakness.isomorphic_variant_count(occ), 1)
        self.assertEqual(weakness.isomorphic_variant_count([]), 0)
        # Dict shape accepted.
        dicts = [
            {"problem_id": "PY-C1-001", "isomorphic_group_id": "ISO-C1-SAME"},
            {"problem_id": "PY-C1-002", "isomorphic_group_id": "ISO-C1-SAME"},
        ]
        self.assertEqual(weakness.isomorphic_variant_count(dicts), 2)

    def test_has_improved(self):
        good = [(True, None), (True, None), (True, None)]
        self.assertTrue(weakness.has_improved(good, "C1-M01"))
        # Recurrence blocks improvement.
        bad = [(True, None), (True, "C1-M01"), (True, None)]
        self.assertFalse(weakness.has_improved(bad, "C1-M01"))
        # A failure blocks improvement.
        failed = [(True, None), (False, None), (True, None)]
        self.assertFalse(weakness.has_improved(failed, "C1-M01"))
        # Needs a full window of 3.
        short = [(True, None), (True, None)]
        self.assertFalse(weakness.has_improved(short, "C1-M01"))
        # Dict shape accepted.
        dicts = [
            {"passed": True, "misconception_id": None},
            {"passed": True, "misconception_id": None},
            {"passed": True, "misconception_id": None},
        ]
        self.assertTrue(weakness.has_improved(dicts, "C1-M01"))

    def test_threshold_constants(self):
        self.assertEqual(weakness.RECENT_WINDOW, 5)
        self.assertEqual(weakness.RECENT_THRESHOLD, 2)
        self.assertEqual(weakness.HISTORICAL_THRESHOLD, 3)
        self.assertEqual(weakness.VARIANT_THRESHOLD, 2)
        self.assertEqual(weakness.IMPROVEMENT_WINDOW, 3)


if __name__ == "__main__":
    unittest.main()
