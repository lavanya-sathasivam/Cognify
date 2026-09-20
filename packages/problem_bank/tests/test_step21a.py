"""Unit tests for Step 21A: Java C3 problem bank + multi-language loader.

Scope (ONLY Step 21A):
- Two new Java C3 problems load and validate through the EXISTING
  ``packages.problem_schema.Problem`` path (no new schema).
- The loader discovers both ``problem-bank/python`` and
  ``problem-bank/java`` via the new explicit ``*_all`` helpers while the
  existing default callers still see the Python-only bank (24 problems).
- No execution-service, student.py, learner, mastery, adaptive,
  diagnosis, or verification changes are exercised here: reference
  outputs are validated by PURE re-implementations of each spec (no
  submission string is ever executed on the host).

Run from repo root:
    python -m unittest packages.problem_bank.tests.test_step21a -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# -- sys.path bootstrap (repo root only) ------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.problem_bank import loader as bank_loader  # noqa: E402
from packages.problem_schema.models import Problem  # noqa: E402
from packages.taxonomy import (  # noqa: E402
    get_misconception,
    is_valid_misconception,
    misconception_belongs_to,
)

JAVA_CANONICAL_ID = "JAVA-C3-COUNT-DIV"
JAVA_TRANSFER_ID = "JAVA-C3-COUNT-DIV-TRANSFER"
JAVA_GROUP = "ISO-C3-COUNT-DIV-JAVA"

PY_CANONICAL_ID = "PY-C3-COUNT-DIV"
PY_TRANSFER_ID = "PY-C3-COUNT-DIV-TRANSFER"


# ---------------------------------------------------------------------------
# Pure spec re-implementations (validate test DATA, never execute submissions)
# ---------------------------------------------------------------------------
def _java_canonical(stdin_data: str) -> str:
    """Mirror of the Java countDivisible reference: count x % k == 0."""
    parts = stdin_data.strip().split()
    n, k = int(parts[0]), int(parts[1])
    nums = list(map(int, parts[2:2 + n]))
    return str(sum(1 for x in nums if x % k == 0))


def _java_transfer(stdin_data: str) -> str:
    """Mirror of the Java countColdDays reference: count t < threshold."""
    parts = stdin_data.strip().split()
    n, threshold = int(parts[0]), int(parts[1])
    temps = list(map(int, parts[2:2 + n]))
    return str(sum(1 for t in temps if t < threshold))


# ---------------------------------------------------------------------------
# 1: Java problem loading + language metadata + schema validation
# ---------------------------------------------------------------------------
class JavaProblemLoadTests(unittest.TestCase):
    def test_java_canonical_loads_with_expected_metadata(self):
        problem = bank_loader.load_problem_all(JAVA_CANONICAL_ID)
        self.assertEqual(problem.problem_id, JAVA_CANONICAL_ID)
        self.assertEqual(problem.language, "java")
        self.assertEqual(problem.concept_id, "C3")
        self.assertEqual(problem.difficulty, 2)
        self.assertEqual(problem.variant_role, "canonical")
        self.assertEqual(problem.isomorphic_group_id, JAVA_GROUP)
        self.assertEqual(problem.misconception_ids, ("C3-M01", "C3-M04"))
        self.assertTrue(problem.title.strip())
        self.assertTrue(problem.description.strip())
        self.assertTrue(problem.starter_code.strip())
        self.assertTrue(problem.input_format.strip())
        self.assertTrue(problem.output_format.strip())
        self.assertGreaterEqual(len(problem.constraints), 1)
        self.assertEqual(len(problem.public_tests), 2)
        self.assertEqual(len(problem.hidden_tests), 3)
        self.assertEqual(len(problem.test_ids()), 5)
        self.assertEqual(len(set(problem.test_ids())), 5)
        # Round-trip through the schema dict preserves equality.
        self.assertEqual(Problem.from_dict(problem.to_dict()), problem)

    def test_java_transfer_loads_with_expected_metadata(self):
        problem = bank_loader.load_problem_all(JAVA_TRANSFER_ID)
        self.assertEqual(problem.problem_id, JAVA_TRANSFER_ID)
        self.assertEqual(problem.language, "java")
        self.assertEqual(problem.concept_id, "C3")
        self.assertEqual(problem.difficulty, 2)
        self.assertEqual(problem.variant_role, "transfer")
        self.assertEqual(problem.isomorphic_group_id, JAVA_GROUP)
        self.assertEqual(problem.misconception_ids, ("C3-M01", "C3-M04"))
        self.assertEqual(Problem.from_dict(problem.to_dict()), problem)

    def test_java_files_load_directly_and_via_explicit_java_dir(self):
        java_dir = bank_loader.DEFAULT_BANK_ROOT / "java"
        for pid, filename in (
            (JAVA_CANONICAL_ID, "JAVA-C3-COUNT-DIV.json"),
            (JAVA_TRANSFER_ID, "JAVA-C3-COUNT-DIV-TRANSFER.json"),
        ):
            from_file = bank_loader.load_problem_file(java_dir / filename)
            self.assertEqual(from_file.problem_id, pid)
            self.assertEqual(from_file.language, "java")
            via_dir = bank_loader.load_problem(pid, bank_dir=java_dir)
            self.assertEqual(via_dir, from_file)
            via_all = bank_loader.load_problem_all(pid)
            self.assertEqual(via_all, from_file)

    def test_java_reference_logic_matches_all_expected_outputs(self):
        canonical = bank_loader.load_problem_all(JAVA_CANONICAL_ID)
        for case in canonical.all_tests():
            self.assertEqual(
                _java_canonical(case.input),
                case.expected_output,
                f"canonical test {case.id} data disagrees with the spec",
            )
        transfer = bank_loader.load_problem_all(JAVA_TRANSFER_ID)
        for case in transfer.all_tests():
            self.assertEqual(
                _java_transfer(case.input),
                case.expected_output,
                f"transfer test {case.id} data disagrees with the spec",
            )

    def test_java_misconceptions_belong_to_c3_and_cover_java(self):
        for pid in (JAVA_CANONICAL_ID, JAVA_TRANSFER_ID):
            problem = bank_loader.load_problem_all(pid)
            for mid in problem.misconception_ids:
                self.assertTrue(is_valid_misconception(mid), f"{pid}/{mid}")
                self.assertTrue(
                    misconception_belongs_to(mid, "C3"),
                    f"{pid}/{mid} wrong concept",
                )
                self.assertIn(
                    "java", get_misconception(mid).languages, f"{pid}/{mid}"
                )

    def test_java_starter_code_follows_execution_service_convention(self):
        # Must match services/execution-service/app/java_runner.py:
        # submission defines ``public class Main`` in ``Main.java`` and
        # reads the test input from stdin.
        for pid, method in (
            (JAVA_CANONICAL_ID, "countDivisible"),
            (JAVA_TRANSFER_ID, "countColdDays"),
        ):
            problem = bank_loader.load_problem_all(pid)
            code = problem.starter_code
            self.assertIn("public class Main", code, pid)
            self.assertIn("public static void main", code, pid)
            self.assertIn("System.in", code, pid)
            self.assertIn(method, code, pid)
            self.assertIn("TODO", code, pid)

    def test_java_schema_rejects_bad_language_and_wrong_concept_misc(self):
        good = bank_loader.load_problem_all(JAVA_CANONICAL_ID).to_dict()
        bad_lang = dict(good, language="ruby")
        with self.assertRaises(ValueError):
            Problem.from_dict(bad_lang)
        bad_misc = dict(good, misconception_ids=["C2-M01"])
        with self.assertRaises(ValueError):
            Problem.from_dict(bad_misc)
        bad_role = dict(good, variant_role="isomorphic")
        with self.assertRaises(ValueError):
            Problem.from_dict(bad_role)


# ---------------------------------------------------------------------------
# 2: isomorphic pair consistency (genuine pair, not a renamed copy)
# ---------------------------------------------------------------------------
class JavaIsomorphicPairTests(unittest.TestCase):
    def test_canonical_and_transfer_share_group_but_differ_in_role(self):
        canonical = bank_loader.load_problem_all(JAVA_CANONICAL_ID)
        transfer = bank_loader.load_problem_all(JAVA_TRANSFER_ID)
        self.assertNotEqual(canonical.problem_id, transfer.problem_id)
        self.assertEqual(canonical.concept_id, transfer.concept_id)
        self.assertEqual(canonical.concept_id, "C3")
        self.assertEqual(transfer.concept_id, "C3")
        self.assertEqual(canonical.isomorphic_group_id, JAVA_GROUP)
        self.assertEqual(transfer.isomorphic_group_id, JAVA_GROUP)
        self.assertEqual(canonical.variant_role, "canonical")
        self.assertEqual(transfer.variant_role, "transfer")
        self.assertEqual(canonical.language, "java")
        self.assertEqual(transfer.language, "java")

    def test_pair_has_distinct_surface_story_and_predicate(self):
        canonical = bank_loader.load_problem_all(JAVA_CANONICAL_ID)
        transfer = bank_loader.load_problem_all(JAVA_TRANSFER_ID)
        self.assertNotEqual(canonical.title, transfer.title)
        self.assertNotEqual(canonical.description, transfer.description)
        self.assertNotEqual(canonical.starter_code, transfer.starter_code)
        # Different filter predicates: divisibility vs strict threshold.
        self.assertIn("%", canonical.starter_code + canonical.description)
        self.assertIn("threshold", transfer.starter_code + transfer.description)

    def test_variants_are_not_interchangeable(self):
        # Transfer P1 uses threshold 0 as the divisor slot: the canonical
        # predicate (x % k == 0) is undefined there, while transfer expects 2.
        transfer = bank_loader.load_problem_all(JAVA_TRANSFER_ID)
        p1 = next(t for t in transfer.all_tests() if t.id == "P1")
        self.assertEqual(p1.expected_output, "2")
        parts = p1.input.strip().split()
        self.assertEqual(int(parts[1]), 0)  # would be div-by-zero for % k
        # Canonical P1 under the transfer predicate (t < k=2) yields 1,
        # but canonical expects 2 — the predicates genuinely differ.
        canonical = bank_loader.load_problem_all(JAVA_CANONICAL_ID)
        cp1 = next(t for t in canonical.all_tests() if t.id == "P1")
        cparts = cp1.input.strip().split()
        ck = int(cparts[1])
        cnums = list(map(int, cparts[2:]))
        self.assertEqual(
            str(sum(1 for t in cnums if t < ck)),
            "1",
        )
        self.assertEqual(cp1.expected_output, "2")

    def test_java_group_is_distinct_from_python_group(self):
        java_canonical = bank_loader.load_problem_all(JAVA_CANONICAL_ID)
        py_canonical = bank_loader.load_problem(PY_CANONICAL_ID)
        self.assertEqual(py_canonical.isomorphic_group_id, "ISO-C3-COUNT-DIV")
        self.assertNotEqual(
            java_canonical.isomorphic_group_id,
            py_canonical.isomorphic_group_id,
        )


# ---------------------------------------------------------------------------
# 3: backward compatibility — Python bank unchanged
# ---------------------------------------------------------------------------
class PythonBackwardCompatTests(unittest.TestCase):
    def test_default_bank_dir_still_python_only(self):
        self.assertEqual(
            bank_loader.DEFAULT_BANK_DIR,
            bank_loader.DEFAULT_BANK_ROOT / "python",
        )
        self.assertEqual(
            bank_loader.SUPPORTED_BANK_LANGUAGES, ("python", "java")
        )

    def test_default_load_still_sees_24_python_problems(self):
        ids = bank_loader.list_problem_ids()
        self.assertEqual(len(ids), 24)
        self.assertEqual(len(set(ids)), 24)
        self.assertNotIn(JAVA_CANONICAL_ID, ids)
        self.assertNotIn(JAVA_TRANSFER_ID, ids)
        self.assertIn(PY_CANONICAL_ID, ids)
        self.assertIn(PY_TRANSFER_ID, ids)
        self.assertEqual(len(bank_loader.load_all_problems()), 24)

    def test_python_c3_problems_completely_unchanged(self):
        canonical = bank_loader.load_problem(PY_CANONICAL_ID)
        self.assertEqual(canonical.title, "Count Divisible Numbers")
        self.assertEqual(canonical.language, "python")
        self.assertEqual(canonical.concept_id, "C3")
        self.assertEqual(canonical.variant_role, "canonical")
        self.assertEqual(canonical.isomorphic_group_id, "ISO-C3-COUNT-DIV")
        self.assertEqual(canonical.misconception_ids, ("C3-M01", "C3-M04"))
        self.assertEqual(
            [(t.id, t.input, t.expected_output) for t in canonical.public_tests],
            [
                ("P1", "5 2\n1 2 3 4 5\n", "2"),
                ("P2", "4 3\n3 6 7 9\n", "3"),
            ],
        )
        transfer = bank_loader.load_problem(PY_TRANSFER_ID)
        self.assertEqual(transfer.language, "python")
        self.assertEqual(transfer.variant_role, "transfer")
        self.assertEqual(transfer.isomorphic_group_id, "ISO-C3-COUNT-DIV")

    def test_default_load_problem_does_not_leak_java(self):
        with self.assertRaises(ValueError):
            bank_loader.load_problem(JAVA_CANONICAL_ID)


# ---------------------------------------------------------------------------
# 4: combined loader behavior + uniqueness
# ---------------------------------------------------------------------------
class CombinedLoaderTests(unittest.TestCase):
    def test_combined_bank_holds_26_problems_with_no_duplicates(self):
        ids = bank_loader.list_problem_ids_all()
        self.assertEqual(len(ids), 26)
        self.assertEqual(len(set(ids)), 26)
        self.assertEqual(ids, sorted(ids))
        self.assertIn(JAVA_CANONICAL_ID, ids)
        self.assertIn(JAVA_TRANSFER_ID, ids)
        self.assertIn(PY_CANONICAL_ID, ids)
        problems = bank_loader.load_all_problems_all()
        self.assertEqual(len(problems), 26)
        self.assertEqual(sorted(problems), ids)
        self.assertEqual(
            problems[JAVA_CANONICAL_ID].language, "java"
        )
        self.assertEqual(
            problems[PY_CANONICAL_ID].language, "python"
        )

    def test_combined_loader_is_deterministic(self):
        first = bank_loader.load_all_problems_all()
        second = bank_loader.load_all_problems_all()
        self.assertEqual(
            {pid: p.to_dict() for pid, p in first.items()},
            {pid: p.to_dict() for pid, p in second.items()},
        )
        self.assertEqual(
            bank_loader.list_problem_ids_all(),
            bank_loader.list_problem_ids_all(),
        )

    def test_load_problem_all_rejects_unknown_and_bad_input(self):
        with self.assertRaises(ValueError):
            bank_loader.load_problem_all("NO-SUCH-PROBLEM")
        with self.assertRaises(ValueError):
            bank_loader.load_problem_all("   ")
        with self.assertRaises(TypeError):
            bank_loader.load_problem_all(123)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            bank_loader.load_all_problems_all(
                bank_loader.DEFAULT_BANK_ROOT / "missing-root"
            )


if __name__ == "__main__":
    unittest.main()
