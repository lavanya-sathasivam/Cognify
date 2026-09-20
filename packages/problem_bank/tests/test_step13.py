"""Unit tests for Step 13: Problem Bank Expansion (transfer + probe).

Bank under test (all Python, all C3, all validated through the EXISTING
``packages.problem_schema.Problem`` path — no new schema):

    PY-C3-COUNT-DIV            canonical   ISO-C3-COUNT-DIV     (Step 12, unchanged)
    PY-C3-COUNT-DIV-TRANSFER   transfer    ISO-C3-COUNT-DIV     (new: temperature story)
    PY-C3-LOOP-MISCONCEPTION   remedial    ISO-C3-INCLUSIVE-SUM (new: C3-M05 probe)

Reference outputs are validated by PURE re-implementations of each spec
(no submission string is ever executed). The transfer-vs-canonical
distinctness proof is functional: each spec's reference logic fails the
other spec's tests, so neither problem is a renamed copy of the other.

Run from repo root:
    python -m unittest discover -s packages/problem_bank/tests -t . -v
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# -- sys.path bootstrap (repo root only) ------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.problem_bank import loader as bank_loader  # noqa: E402
from packages.problem_bank import pipeline as pipe  # noqa: E402
from packages.problem_schema.models import (  # noqa: E402
    VALID_VARIANT_ROLES,
    Problem,
)
from packages.taxonomy import (  # noqa: E402
    get_misconception,
    is_valid_misconception,
    misconception_belongs_to,
)

CANONICAL_ID = "PY-C3-COUNT-DIV"
TRANSFER_ID = "PY-C3-COUNT-DIV-TRANSFER"
PROBE_ID = "PY-C3-LOOP-MISCONCEPTION"

EXPECTED_IDS = sorted([CANONICAL_ID, TRANSFER_ID, PROBE_ID])


# ---------------------------------------------------------------------------
# Pure spec re-implementations (validate test DATA, never execute submissions)
# ---------------------------------------------------------------------------
def _canonical_reference(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    n, k = int(parts[0]), int(parts[1])
    nums = list(map(int, parts[2:2 + n]))
    count = 0
    for x in nums:
        if x % k == 0:
            count += 1
    return str(count)


def _transfer_reference(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    n, threshold = int(parts[0]), int(parts[1])
    temps = list(map(int, parts[2:2 + n]))
    count = 0
    for t in temps:
        if t < threshold:
            count += 1
    return str(count)


def _probe_reference(stdin_data: str) -> str:
    n = int(stdin_data.strip().split()[0])
    total = 0
    for i in range(1, n + 1):
        total += i
    return str(total)


def _probe_m05_buggy(stdin_data: str) -> str:
    """The C3-M05 mistake: range(1, n) drops the final value."""
    n = int(stdin_data.strip().split()[0])
    total = 0
    for i in range(1, n):
        total += i
    return str(total)


def _starter_function_name(starter_code: str) -> str:
    match = re.search(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", starter_code, re.M)
    assert match is not None, "starter_code must define a function"
    return match.group(1)


def _failed_result_dict(problem: Problem, failing_test_id: str) -> dict:
    """Minimal internal-result dict with a hidden decisive failure."""
    tests = []
    for case in problem.all_tests():
        failed = case.id == failing_test_id
        tests.append(
            {
                "test_id": case.id,
                "passed": not failed,
                "input": case.input,
                "expected_output": case.expected_output,
                "actual_output": "999\n" if failed else case.expected_output,
                "stdout": "999\n" if failed else case.expected_output,
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "time_ms": 5,
            }
        )
    decisive = next(t for t in tests if t["test_id"] == failing_test_id)
    return {
        "status": "FAILED",
        "language": "python",
        "execution_time_ms": 25,
        "stdout": decisive["stdout"],
        "stderr": "",
        "tests": tests,
        "passed_count": len(tests) - 1,
        "failed_count": 1,
        "failed_test_id": failing_test_id,
        "expected_output": decisive["expected_output"],
        "actual_output": decisive["actual_output"],
    }


# ---------------------------------------------------------------------------
# 1-3, 13-14: discovery, schema validation, canonical unchanged
# ---------------------------------------------------------------------------
class BankDiscoveryTests(unittest.TestCase):
    def test_all_three_problems_load(self):
        # Step 19 expansion note: the bank now covers C1-C8 (24 problems),
        # so this asserts the Step 13 C3 trio is present with unchanged
        # loading behavior (superset-tolerant) rather than bank-singleton
        # equality. Bank-wide uniqueness/counts live in test_step19.py.
        ids = bank_loader.list_problem_ids()
        for pid in EXPECTED_IDS:
            self.assertIn(pid, ids)
            problem = bank_loader.load_problem(pid)
            self.assertEqual(problem.problem_id, pid)

    def test_all_pass_problem_schema_validation(self):
        for pid in EXPECTED_IDS:
            problem = bank_loader.load_problem(pid)
            self.assertIsInstance(problem, Problem)
            # Round-trip through the schema dict preserves equality.
            self.assertEqual(Problem.from_dict(problem.to_dict()), problem)
            for field in (
                "title",
                "description",
                "starter_code",
                "input_format",
                "output_format",
            ):
                self.assertTrue(
                    getattr(problem, field).strip(), f"{pid}.{field} empty"
                )
            self.assertGreaterEqual(len(problem.constraints), 1)
            self.assertGreaterEqual(len(problem.public_tests), 1)
            self.assertGreaterEqual(len(problem.test_ids()), 2)
            self.assertEqual(len(problem.test_ids()), len(set(problem.test_ids())))
            self.assertIn(problem.variant_role, VALID_VARIANT_ROLES)
            self.assertGreaterEqual(len(problem.misconception_ids), 1)

    def test_canonical_metadata_unchanged(self):
        problem = bank_loader.load_problem(CANONICAL_ID)
        self.assertEqual(problem.concept_id, "C3")
        self.assertEqual(problem.language, "python")
        self.assertEqual(problem.difficulty, 2)
        self.assertEqual(problem.title, "Count Divisible Numbers")
        self.assertEqual(problem.variant_role, "canonical")
        self.assertEqual(problem.isomorphic_group_id, "ISO-C3-COUNT-DIV")
        self.assertEqual(problem.misconception_ids, ("C3-M01", "C3-M04"))
        self.assertEqual(
            [(t.id, t.input, t.expected_output) for t in problem.public_tests],
            [
                ("P1", "5 2\n1 2 3 4 5\n", "2"),
                ("P2", "4 3\n3 6 7 9\n", "3"),
            ],
        )
        self.assertEqual(
            [(t.id, t.input, t.expected_output) for t in problem.hidden_tests],
            [
                ("H1", "1 5\n3\n", "0"),
                ("H2", "6 2\n2 4 6 8 10 12\n", "6"),
                ("H3", "3 1\n7 8 9\n", "3"),
            ],
        )

    def test_loader_discovers_all_three(self):
        all_problems = bank_loader.load_all_problems()
        for pid in EXPECTED_IDS:
            self.assertIn(pid, sorted(all_problems))

    def test_no_duplicate_problem_ids(self):
        ids = bank_loader.list_problem_ids()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(bank_loader.load_all_problems()), 3)


# ---------------------------------------------------------------------------
# 4-8: isomorphic transfer relationship + meaningful surface difference
# ---------------------------------------------------------------------------
class TransferRelationTests(unittest.TestCase):
    def test_transfer_has_same_concept_as_canonical(self):
        canonical = bank_loader.load_problem(CANONICAL_ID)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self.assertEqual(transfer.concept_id, canonical.concept_id)
        self.assertEqual(transfer.concept_id, "C3")

    def test_transfer_has_same_isomorphic_group(self):
        canonical = bank_loader.load_problem(CANONICAL_ID)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self.assertEqual(
            transfer.isomorphic_group_id, canonical.isomorphic_group_id
        )
        self.assertEqual(transfer.isomorphic_group_id, "ISO-C3-COUNT-DIV")

    def test_transfer_has_different_problem_id(self):
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self.assertEqual(transfer.problem_id, TRANSFER_ID)
        self.assertNotEqual(transfer.problem_id, CANONICAL_ID)

    def test_transfer_has_variant_role_transfer(self):
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self.assertEqual(transfer.variant_role, "transfer")

    def test_transfer_difficulty_matches_canonical_range(self):
        canonical = bank_loader.load_problem(CANONICAL_ID)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self.assertEqual(transfer.difficulty, canonical.difficulty)

    def test_transfer_surface_differs_meaningfully(self):
        canonical = bank_loader.load_problem(CANONICAL_ID)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self.assertNotEqual(transfer.title, canonical.title)
        self.assertNotEqual(transfer.description, canonical.description)
        self.assertNotEqual(transfer.input_format, canonical.input_format)
        # Domain vocabulary belongs to exactly one surface story. The
        # transfer description documents its relationship to the canonical
        # ('... transfer variant of ...') after the task statement, so the
        # task portion (before that marker) is what must differ.
        task_portion = transfer.description.lower().split("transfer variant")[0]
        self.assertIn("divisible", canonical.description.lower())
        self.assertNotIn("divisible", task_portion)
        for keyword in ("threshold", "temperature", "cold"):
            self.assertIn(keyword, task_portion)
            self.assertNotIn(keyword, canonical.description.lower())
        # Different entry-point function: not a variable rename.
        self.assertNotEqual(
            _starter_function_name(transfer.starter_code),
            _starter_function_name(canonical.starter_code),
        )
        self.assertEqual(
            _starter_function_name(transfer.starter_code), "count_cold_days"
        )
        # Disjoint test data: no shared stdin across the pair.
        canonical_inputs = {t.input for t in canonical.all_tests()}
        transfer_inputs = {t.input for t in transfer.all_tests()}
        self.assertTrue(canonical_inputs.isdisjoint(transfer_inputs))

    def test_transfer_is_not_a_renamed_copy(self):
        """Functional proof: each spec's logic fails the other's tests."""
        canonical = bank_loader.load_problem(CANONICAL_ID)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        # Transfer logic (threshold comparison) disagrees with canonical
        # expectations on canonical inputs.
        disagreements = [
            case.id
            for case in canonical.all_tests()
            if _transfer_reference(case.input) != case.expected_output
        ]
        self.assertGreater(len(disagreements), 0)
        # Canonical logic (modulo) cannot even run on transfer inputs with
        # threshold 0, and disagrees where it can run.
        zero_threshold = next(
            case for case in transfer.all_tests() if case.input.startswith("5 0\n")
        )
        with self.assertRaises(ZeroDivisionError):
            _canonical_reference(zero_threshold.input)
        runnable = [
            case
            for case in transfer.all_tests()
            if not case.input.startswith("5 0\n")
        ]
        self.assertTrue(
            any(
                _canonical_reference(case.input) != case.expected_output
                for case in runnable
            )
        )


# ---------------------------------------------------------------------------
# 9-10: misconception probe (existing C3-M05, boundary coverage)
# ---------------------------------------------------------------------------
class MisconceptionProbeTests(unittest.TestCase):
    def test_probe_uses_an_existing_c3_misconception(self):
        probe = bank_loader.load_problem(PROBE_ID)
        self.assertEqual(probe.misconception_ids, ("C3-M05",))
        self.assertTrue(is_valid_misconception("C3-M05"))
        self.assertTrue(misconception_belongs_to("C3-M05", "C3"))
        self.assertTrue(misconception_belongs_to("C3-M05", probe.concept_id))
        # C3-M05 is Python-scoped, matching this Python probe.
        self.assertIn("python", get_misconception("C3-M05").languages)

    def test_probe_has_supported_variant_role_and_own_group(self):
        probe = bank_loader.load_problem(PROBE_ID)
        self.assertEqual(probe.variant_role, "remedial")
        self.assertIn(probe.variant_role, VALID_VARIANT_ROLES)
        self.assertEqual(probe.concept_id, "C3")
        self.assertEqual(probe.language, "python")
        # Distinct task family from the COUNT-DIV pair.
        self.assertNotEqual(probe.isomorphic_group_id, "ISO-C3-COUNT-DIV")
        self.assertEqual(probe.isomorphic_group_id, "ISO-C3-INCLUSIVE-SUM")

    def test_probe_has_appropriate_boundary_coverage(self):
        probe = bank_loader.load_problem(PROBE_ID)
        inputs = [t.input for t in probe.all_tests()]
        # The n = 1 razor edge: inclusive reasoning gives 1, the M05
        # mistake (range(1, n)) gives 0.
        self.assertIn("1\n", inputs)
        self.assertIn("2\n", inputs)
        # Every test discriminates: the M05-buggy output differs from
        # expected on all five tests, including the n = 1 boundary.
        for case in probe.all_tests():
            self.assertNotEqual(
                _probe_m05_buggy(case.input),
                case.expected_output,
                f"M05 mistake undetectable on {case.id}",
            )
        edge = next(case for case in probe.all_tests() if case.input == "1\n")
        self.assertEqual(edge.expected_output, "1")
        self.assertEqual(_probe_m05_buggy(edge.input), "0")
        # The probe claims evidence, not deterministic detection.
        self.assertIn("evidence", probe.description.lower())


# ---------------------------------------------------------------------------
# 11: deterministic expected outputs for canonical + transfer
# ---------------------------------------------------------------------------
class DeterministicOutputTests(unittest.TestCase):
    def test_canonical_and_transfer_outputs_match_specs(self):
        for pid, reference in (
            (CANONICAL_ID, _canonical_reference),
            (TRANSFER_ID, _transfer_reference),
            (PROBE_ID, _probe_reference),
        ):
            problem = bank_loader.load_problem(pid)
            for case in problem.all_tests():
                self.assertEqual(
                    reference(case.input),
                    case.expected_output,
                    f"{pid} {case.id} data disagrees with the spec",
                )

    def test_transfer_expected_values_are_correct(self):
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self.assertEqual(
            [(t.id, t.expected_output) for t in transfer.all_tests()],
            [("P1", "2"), ("P2", "2"), ("H1", "0"), ("H2", "6"), ("H3", "0")],
        )


# ---------------------------------------------------------------------------
# 12, 15: hidden protection + language isolation for the new problems
# ---------------------------------------------------------------------------
class ProtectionIsolationTests(unittest.TestCase):
    def test_hidden_expected_outputs_remain_protected(self):
        for pid, failing_id, failing_expected in (
            (TRANSFER_ID, "H1", "0"),
            (PROBE_ID, "H3", "5050"),
        ):
            problem = bank_loader.load_problem(pid)
            internal = _failed_result_dict(problem, failing_id)
            view = pipe.to_student_view(problem, internal)
            hidden_ids = {t.id for t in problem.hidden_tests}
            for entry in view["tests"]:
                if entry["test_id"] in hidden_ids:
                    self.assertIsNone(entry["expected_output"])
                else:
                    self.assertIsNotNone(entry["expected_output"])
            self.assertIsNone(view["expected_output"])
            self.assertEqual(internal["expected_output"], failing_expected)

    def test_no_accidental_cross_language_metadata(self):
        for pid in EXPECTED_IDS:
            problem = bank_loader.load_problem(pid)
            self.assertEqual(problem.language, "python")
            for mid in problem.misconception_ids:
                self.assertTrue(misconception_belongs_to(mid, "C3"))
                self.assertIn("python", get_misconception(mid).languages)


if __name__ == "__main__":
    unittest.main()
