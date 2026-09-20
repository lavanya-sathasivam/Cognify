"""Unit tests for Step 19: Problem Bank Expansion (C1-C8, Python).

Bank under test (all Python, all validated through the EXISTING
``packages.problem_schema.Problem`` path — no new schema):

    C1: PY-C1-TEMP-CONVERT (canonical) / PY-C1-AVG-PAIR (remedial) /
        PY-C1-TEMP-CONVERT-TRANSFER (transfer, Hours From Minutes)
    C2: PY-C2-GRADE-BAND (canonical) / PY-C2-EITHER-OR (remedial) /
        PY-C2-GRADE-BAND-TRANSFER (transfer, Parcel Shipping Class)
    C3: existing trio, unchanged (COUNT-DIV / COUNT-DIV-TRANSFER / LOOP-MISCONCEPTION)
    C4: PY-C4-RECT-METRICS (canonical) / PY-C4-DOUBLE-IT (remedial) /
        PY-C4-RECT-METRICS-TRANSFER (transfer, Box Volume and Surface)
    C5: PY-C5-FIND-MAX (canonical) / PY-C5-LAST-ITEM (remedial) /
        PY-C5-FIND-MAX-TRANSFER (transfer, Longest Word)
    C6: PY-C6-COUNT-WORD (canonical) / PY-C6-SAFE-LOOKUP (remedial) /
        PY-C6-COUNT-WORD-TRANSFER (transfer, Stock Totals)
    C7: PY-C7-BANK-ACCOUNT (canonical) / PY-C7-COUNTER (remedial) /
        PY-C7-BANK-ACCOUNT-TRANSFER (transfer, Shopping Cart Totals)
    C8: PY-C8-FACTORIAL (canonical, recursion family) /
        PY-C8-RECURSIVE-SUM (remedial) /
        PY-C8-FACTORIAL-TRANSFER (transfer, Recursive Integer Power)

Reference outputs are validated by PURE re-implementations of each spec
(no submission string is ever executed on the host). Transfer
distinctness is functional: each family's canonical reference logic
disagrees with (or cannot run on) the transfer tests and vice versa, so
no transfer is a renamed copy.

No new deterministic diagnosis rules are claimed: only C3-M01/C3-M05
have specialized rules, and no new problem lists them, so new failures
honestly fall through to the existing fallback/LLM path.

Run from repo root:
    python -m unittest discover -s packages/problem_bank/tests -t . -v
"""
from __future__ import annotations

import math
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
from packages.problem_schema.models import (  # noqa: E402
    VALID_VARIANT_ROLES,
    Problem,
)
from packages.taxonomy import (  # noqa: E402
    CONCEPT_IDS,
    get_misconception,
    is_valid_misconception,
    misconception_belongs_to,
)

# -- Step 19 families: (canonical, remedial, transfer, concept) -------------
FAMILIES: tuple[tuple[str, str, str, str], ...] = (
    ("PY-C1-TEMP-CONVERT", "PY-C1-AVG-PAIR", "PY-C1-TEMP-CONVERT-TRANSFER", "C1"),
    ("PY-C2-GRADE-BAND", "PY-C2-EITHER-OR", "PY-C2-GRADE-BAND-TRANSFER", "C2"),
    ("PY-C3-COUNT-DIV", "PY-C3-LOOP-MISCONCEPTION", "PY-C3-COUNT-DIV-TRANSFER", "C3"),
    ("PY-C4-RECT-METRICS", "PY-C4-DOUBLE-IT", "PY-C4-RECT-METRICS-TRANSFER", "C4"),
    ("PY-C5-FIND-MAX", "PY-C5-LAST-ITEM", "PY-C5-FIND-MAX-TRANSFER", "C5"),
    ("PY-C6-COUNT-WORD", "PY-C6-SAFE-LOOKUP", "PY-C6-COUNT-WORD-TRANSFER", "C6"),
    ("PY-C7-BANK-ACCOUNT", "PY-C7-COUNTER", "PY-C7-BANK-ACCOUNT-TRANSFER", "C7"),
    ("PY-C8-FACTORIAL", "PY-C8-RECURSIVE-SUM", "PY-C8-FACTORIAL-TRANSFER", "C8"),
)

EXPECTED_IDS: list[str] = sorted(
    pid for family in FAMILIES for pid in family[:3]
)

# Deterministic rules exist only for these C3 targets (Step 15).
RULE_TARGETS: frozenset[str] = frozenset({"C3-M01", "C3-M05"})


# ---------------------------------------------------------------------------
# Pure spec re-implementations (validate test DATA, never execute submissions)
# ---------------------------------------------------------------------------
def _c1_canonical(stdin_data: str) -> str:
    f = int(stdin_data.strip().split()[0])
    return f"{(f - 32) * 5 / 9:.1f}"


def _c1_remedial(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    return f"{(int(parts[0]) + int(parts[1])) / 2:.1f}"


def _c1_transfer(stdin_data: str) -> str:
    return f"{int(stdin_data.strip().split()[0]) / 60:.1f}"


def _c2_canonical(stdin_data: str) -> str:
    v = int(stdin_data.strip().split()[0])
    if v >= 85:
        return "DISTINCTION"
    if v >= 65:
        return "MERIT"
    if v >= 50:
        return "PASS"
    return "FAIL"


def _c2_remedial(stdin_data: str) -> str:
    return "YES" if int(stdin_data.strip().split()[0]) in (5, 10) else "NO"


def _c2_transfer(stdin_data: str) -> str:
    v = int(stdin_data.strip().split()[0])
    if v >= 50:
        return "FREIGHT"
    if v >= 10:
        return "STANDARD"
    if v >= 1:
        return "LIGHT"
    return "INVALID"


def _c3_canonical(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    n, k = int(parts[0]), int(parts[1])
    nums = list(map(int, parts[2:2 + n]))
    return str(sum(1 for x in nums if x % k == 0))


def _c3_transfer(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    n, threshold = int(parts[0]), int(parts[1])
    temps = list(map(int, parts[2:2 + n]))
    return str(sum(1 for t in temps if t < threshold))


def _c3_remedial(stdin_data: str) -> str:
    n = int(stdin_data.strip().split()[0])
    return str(n * (n + 1) // 2)


def _c4_canonical(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    w, h = int(parts[0]), int(parts[1])
    return f"{w * h} {2 * (w + h)}"


def _c4_remedial(stdin_data: str) -> str:
    return str(2 * int(stdin_data.strip().split()[0]))


def _c4_transfer(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    l, w, h = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{l * w * h} {2 * (l * w + w * h + h * l)}"


def _c5_canonical(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    n = int(parts[0])
    return str(max(map(int, parts[1:1 + n])))


def _c5_remedial(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    return str(int(parts[int(parts[0])]))


def _c5_transfer(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    words = parts[1:1 + int(parts[0])]
    best = words[0]
    for w in words[1:]:
        if len(w) > len(best):
            best = w
    return best


def _c6_canonical(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    n = int(parts[0])
    return str(parts[1:1 + n].count(parts[1 + n]))


def _c6_remedial(stdin_data: str) -> str:
    return str({"apple": 5, "banana": 3}.get(stdin_data.strip().split()[0], 0))


def _c6_transfer(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    n = int(parts[0])
    totals: dict[str, int] = {}
    pos = 1
    for _ in range(n):
        totals[parts[pos]] = totals.get(parts[pos], 0) + int(parts[pos + 1])
        pos += 2
    return str(totals.get(parts[pos], 0))


def _c7_canonical(stdin_data: str) -> str:
    lines = stdin_data.strip().splitlines()
    accounts: dict[str, int] = {}
    out: list[str] = []
    for line in lines[1:1 + int(lines[0].split()[0])]:
        parts = line.split()
        if parts[0] == "OPEN":
            accounts[parts[1]] = int(parts[2])
        elif parts[0] == "DEPOSIT":
            if parts[1] in accounts:
                accounts[parts[1]] += int(parts[2])
        elif parts[0] == "BALANCE":
            out.append(str(accounts[parts[1]]) if parts[1] in accounts else "UNKNOWN")
    return "\n".join(out)


def _c7_remedial(stdin_data: str) -> str:
    lines = stdin_data.strip().splitlines()
    value = 0
    out: list[str] = []
    for line in lines[1:1 + int(lines[0].split()[0])]:
        cmd = line.split()[0]
        if cmd == "INC":
            value += 1
        elif cmd == "DEC":
            value -= 1
        elif cmd == "SHOW":
            out.append(str(value))
    return "\n".join(out)


def _c7_transfer(stdin_data: str) -> str:
    lines = stdin_data.strip().splitlines()
    carts: dict[str, int] = {}
    out: list[str] = []
    for line in lines[1:1 + int(lines[0].split()[0])]:
        parts = line.split()
        if parts[0] == "ADD":
            carts[parts[1]] = carts.get(parts[1], 0) + int(parts[2])
        elif parts[0] == "TOTAL":
            out.append(str(carts[parts[1]]) if parts[1] in carts else "UNKNOWN")
    return "\n".join(out)


def _c8_canonical(stdin_data: str) -> str:
    return str(math.factorial(int(stdin_data.strip().split()[0])))


def _c8_remedial(stdin_data: str) -> str:
    n = int(stdin_data.strip().split()[0])
    return str(n * (n + 1) // 2)


def _c8_transfer(stdin_data: str) -> str:
    parts = stdin_data.strip().split()
    return str(int(parts[0]) ** int(parts[1]))


REFERENCE_BY_ID: dict[str, object] = {
    "PY-C1-TEMP-CONVERT": _c1_canonical,
    "PY-C1-AVG-PAIR": _c1_remedial,
    "PY-C1-TEMP-CONVERT-TRANSFER": _c1_transfer,
    "PY-C2-GRADE-BAND": _c2_canonical,
    "PY-C2-EITHER-OR": _c2_remedial,
    "PY-C2-GRADE-BAND-TRANSFER": _c2_transfer,
    "PY-C3-COUNT-DIV": _c3_canonical,
    "PY-C3-COUNT-DIV-TRANSFER": _c3_transfer,
    "PY-C3-LOOP-MISCONCEPTION": _c3_remedial,
    "PY-C4-RECT-METRICS": _c4_canonical,
    "PY-C4-DOUBLE-IT": _c4_remedial,
    "PY-C4-RECT-METRICS-TRANSFER": _c4_transfer,
    "PY-C5-FIND-MAX": _c5_canonical,
    "PY-C5-LAST-ITEM": _c5_remedial,
    "PY-C5-FIND-MAX-TRANSFER": _c5_transfer,
    "PY-C6-COUNT-WORD": _c6_canonical,
    "PY-C6-SAFE-LOOKUP": _c6_remedial,
    "PY-C6-COUNT-WORD-TRANSFER": _c6_transfer,
    "PY-C7-BANK-ACCOUNT": _c7_canonical,
    "PY-C7-COUNTER": _c7_remedial,
    "PY-C7-BANK-ACCOUNT-TRANSFER": _c7_transfer,
    "PY-C8-FACTORIAL": _c8_canonical,
    "PY-C8-RECURSIVE-SUM": _c8_remedial,
    "PY-C8-FACTORIAL-TRANSFER": _c8_transfer,
}


def _reference_output(problem_id: str, stdin_data: str) -> str:
    """Run a family's pure spec on test DATA. May raise (wrong-arity input
    for a foreign spec counts as distinct, handled by callers)."""
    func = REFERENCE_BY_ID[problem_id]
    assert callable(func)
    return func(stdin_data)  # type: ignore[operator]


def _starter_function_name(starter_code: str) -> str:
    # Entry-point name: the defined class for OOP problems (C7 starters
    # define methods inside a class, so top-level `def main` is not the
    # domain signal), else the first top-level solution function.
    class_match = re.search(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:\(]", starter_code, re.M)
    if class_match is not None:
        return class_match.group(1)
    match = re.search(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", starter_code, re.M)
    assert match is not None, "starter_code must define a function"
    return match.group(1)


# ---------------------------------------------------------------------------
# 1-5: bank-wide coverage, uniqueness, schema validity
# ---------------------------------------------------------------------------
class BankCoverageTests(unittest.TestCase):
    def test_all_twenty_four_problems_load(self):
        ids = bank_loader.list_problem_ids()
        self.assertEqual(ids, EXPECTED_IDS)
        self.assertEqual(len(ids), 24)
        for pid in EXPECTED_IDS:
            self.assertEqual(bank_loader.load_problem(pid).problem_id, pid)

    def test_all_ids_unique(self):
        ids = bank_loader.list_problem_ids()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(bank_loader.load_all_problems()), 24)

    def test_all_pass_problem_schema_validation(self):
        for pid in EXPECTED_IDS:
            problem = bank_loader.load_problem(pid)
            self.assertIsInstance(problem, Problem)
            self.assertEqual(Problem.from_dict(problem.to_dict()), problem)
            for field in (
                "title", "description", "starter_code",
                "input_format", "output_format",
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
            self.assertIn(problem.difficulty, (1, 2, 3))
            self.assertEqual(problem.language, "python")

    def test_all_concepts_covered_with_three_roles(self):
        by_concept: dict[str, list[str]] = {}
        for pid in EXPECTED_IDS:
            problem = bank_loader.load_problem(pid)
            by_concept.setdefault(problem.concept_id, []).append(problem.variant_role)
        self.assertEqual(sorted(by_concept), sorted(CONCEPT_IDS))
        for concept in CONCEPT_IDS:
            self.assertEqual(sorted(by_concept[concept]),
                             ["canonical", "remedial", "transfer"], concept)

    def test_all_misconception_ids_valid_and_python_scoped(self):
        for pid in EXPECTED_IDS:
            problem = bank_loader.load_problem(pid)
            for mid in problem.misconception_ids:
                self.assertTrue(is_valid_misconception(mid), f"{pid}/{mid}")
                self.assertTrue(
                    misconception_belongs_to(mid, problem.concept_id),
                    f"{pid}/{mid} wrong concept",
                )
                self.assertIn(
                    "python", get_misconception(mid).languages, f"{pid}/{mid}"
                )

    def test_c3_trio_unchanged(self):
        canonical = bank_loader.load_problem("PY-C3-COUNT-DIV")
        self.assertEqual(canonical.title, "Count Divisible Numbers")
        self.assertEqual(canonical.variant_role, "canonical")
        self.assertEqual(canonical.isomorphic_group_id, "ISO-C3-COUNT-DIV")
        self.assertEqual(canonical.misconception_ids, ("C3-M01", "C3-M04"))
        transfer = bank_loader.load_problem("PY-C3-COUNT-DIV-TRANSFER")
        self.assertEqual(transfer.variant_role, "transfer")
        self.assertEqual(transfer.isomorphic_group_id, "ISO-C3-COUNT-DIV")
        probe = bank_loader.load_problem("PY-C3-LOOP-MISCONCEPTION")
        self.assertEqual(probe.variant_role, "remedial")
        self.assertEqual(probe.misconception_ids, ("C3-M05",))

    def test_reference_outputs_match_all_test_data(self):
        for pid in EXPECTED_IDS:
            problem = bank_loader.load_problem(pid)
            for case in problem.all_tests():
                self.assertEqual(
                    _reference_output(pid, case.input),
                    case.expected_output,
                    f"{pid} {case.id} data disagrees with the spec",
                )


# ---------------------------------------------------------------------------
# 6: canonical/remedial/transfer role structure per family
# ---------------------------------------------------------------------------
class FamilyStructureTests(unittest.TestCase):
    def test_roles_groups_and_difficulty(self):
        for canonical_id, remedial_id, transfer_id, concept in FAMILIES:
            canonical = bank_loader.load_problem(canonical_id)
            remedial = bank_loader.load_problem(remedial_id)
            transfer = bank_loader.load_problem(transfer_id)
            for problem in (canonical, remedial, transfer):
                self.assertEqual(problem.concept_id, concept)
                self.assertEqual(problem.language, "python")
            self.assertEqual(canonical.variant_role, "canonical")
            self.assertEqual(remedial.variant_role, "remedial")
            self.assertEqual(transfer.variant_role, "transfer")
            # Canonical + transfer share one isomorphic group; the remedial
            # probe is its own targeted task family.
            self.assertEqual(
                transfer.isomorphic_group_id, canonical.isomorphic_group_id
            )
            self.assertNotEqual(
                remedial.isomorphic_group_id, canonical.isomorphic_group_id
            )
            # Remedial isolates the misconception: simpler or equal difficulty.
            self.assertLessEqual(remedial.difficulty, canonical.difficulty)

    def test_remedial_targets_a_canonical_misconception(self):
        for canonical_id, remedial_id, _transfer_id, concept in FAMILIES:
            canonical = bank_loader.load_problem(canonical_id)
            remedial = bank_loader.load_problem(remedial_id)
            if concept == "C3":
                # Pre-existing Step 13 design: the probe targets C3-M05
                # while the canonical lists C3-M01/C3-M04. Preserved as-is.
                self.assertEqual(remedial.misconception_ids, ("C3-M05",))
                continue
            self.assertTrue(
                set(remedial.misconception_ids) & set(canonical.misconception_ids),
                f"{remedial_id} shares no misconception with {canonical_id}",
            )


# ---------------------------------------------------------------------------
# 7: transfer distinctness — functional proof per family
# ---------------------------------------------------------------------------
class TransferDistinctnessTests(unittest.TestCase):
    def test_transfer_surface_differs(self):
        for canonical_id, _remedial_id, transfer_id, _concept in FAMILIES:
            canonical = bank_loader.load_problem(canonical_id)
            transfer = bank_loader.load_problem(transfer_id)
            self.assertNotEqual(transfer.problem_id, canonical.problem_id)
            self.assertNotEqual(transfer.title, canonical.title)
            self.assertNotEqual(transfer.description, canonical.description)
            self.assertNotEqual(
                _starter_function_name(transfer.starter_code),
                _starter_function_name(canonical.starter_code),
            )

    def test_canonical_logic_fails_transfer_tests(self):
        """Blindly reusing the canonical algorithm is wrong on transfer data.

        A foreign spec either disagrees with the expected output or cannot
        run on the foreign input shape at all (arity/parse error) — both
        prove the transfer is not a renamed copy.
        """
        for canonical_id, _remedial_id, transfer_id, _concept in FAMILIES:
            transfer = bank_loader.load_problem(transfer_id)
            mismatches = 0
            for case in transfer.all_tests():
                try:
                    got = _reference_output(canonical_id, case.input)
                except (ValueError, IndexError, KeyError, ZeroDivisionError):
                    mismatches += 1  # cannot even run: structurally distinct
                    continue
                if got != case.expected_output:
                    mismatches += 1
            self.assertGreater(
                mismatches, 0,
                f"{canonical_id} logic solves {transfer_id}: not a transfer",
            )

    def test_transfer_logic_fails_canonical_tests(self):
        for canonical_id, _remedial_id, transfer_id, _concept in FAMILIES:
            canonical = bank_loader.load_problem(canonical_id)
            mismatches = 0
            for case in canonical.all_tests():
                try:
                    got = _reference_output(transfer_id, case.input)
                except (ValueError, IndexError, KeyError, ZeroDivisionError):
                    mismatches += 1
                    continue
                if got != case.expected_output:
                    mismatches += 1
            self.assertGreater(
                mismatches, 0,
                f"{transfer_id} logic solves {canonical_id}: not a transfer",
            )


# ---------------------------------------------------------------------------
# 8: remedial razor tests — the intended misconception fails deterministically
# ---------------------------------------------------------------------------
class RemedialRazorTests(unittest.TestCase):
    def test_c1_integer_division_loses_the_half(self):
        problem = bank_loader.load_problem("PY-C1-AVG-PAIR")
        for case in [t for t in problem.all_tests() if t.id in ("P2", "H2", "H3")]:
            parts = case.input.strip().split()
            buggy = f"{(int(parts[0]) + int(parts[1])) // 2:.1f}"
            self.assertNotEqual(buggy, case.expected_output, case.id)

    def test_c2_truthy_or_always_says_yes(self):
        problem = bank_loader.load_problem("PY-C2-EITHER-OR")

        def _buggy(x: int) -> str:
            return "YES" if (x == 5 or 10) else "NO"  # noqa: SIM108 — the bug itself

        for case in [t for t in problem.all_tests() if t.id in ("P2", "H2", "H3")]:
            self.assertEqual(_buggy(int(case.input.strip())), "YES")
            self.assertEqual(case.expected_output, "NO")

    def test_c4_print_instead_of_return_gives_none(self):
        problem = bank_loader.load_problem("PY-C4-DOUBLE-IT")
        for case in problem.all_tests():
            self.assertNotEqual("None", case.expected_output)

    def test_c5_length_index_crashes(self):
        problem = bank_loader.load_problem("PY-C5-LAST-ITEM")
        for case in problem.all_tests():
            parts = case.input.strip().split()
            nums = list(map(int, parts[1:1 + int(parts[0])]))
            with self.assertRaises(IndexError, msg=case.id):
                _ = nums[len(nums)]

    def test_c6_direct_index_raises_key_error(self):
        problem = bank_loader.load_problem("PY-C6-SAFE-LOOKUP")
        for case in [t for t in problem.all_tests() if t.id in ("P2", "H2", "H3")]:
            with self.assertRaises(KeyError, msg=case.id):
                _ = {"apple": 5, "banana": 3}[case.input.strip()]

    def test_c7_c8_remedials_pin_constructor_and_base_case(self):
        counter = bank_loader.load_problem("PY-C7-COUNTER")
        self.assertIn("self", counter.starter_code)
        self.assertIn("__init__", counter.starter_code)
        # SHOW-first boundary: only a constructed zero-state answers 0.
        edge = next(t for t in counter.all_tests() if t.id == "H1")
        self.assertEqual(
            (_c7_remedial(edge.input), edge.expected_output), ("0", "0")
        )
        recsum = bank_loader.load_problem("PY-C8-RECURSIVE-SUM")
        edge = next(t for t in recsum.all_tests() if t.id == "P2")
        self.assertEqual(edge.input, "1\n")
        self.assertEqual(edge.expected_output, "1")


# ---------------------------------------------------------------------------
# 9: honest diagnosis scope + student-flow compatibility
# ---------------------------------------------------------------------------
class DiagnosisScopeTests(unittest.TestCase):
    def test_no_new_problem_claims_rule_covered_misconceptions(self):
        # Deterministic rules exist only for C3-M01/C3-M05; every non-C3
        # problem must therefore rely on fallback/LLM diagnosis.
        for canonical_id, remedial_id, transfer_id, concept in FAMILIES:
            if concept == "C3":
                continue
            for pid in (canonical_id, remedial_id, transfer_id):
                problem = bank_loader.load_problem(pid)
                self.assertTrue(
                    RULE_TARGETS.isdisjoint(problem.misconception_ids), pid
                )

    def test_student_flow_c3_contract_intact(self):
        # services/core-backend/app/student.py hardcodes this trio; the
        # expansion must keep the demo flow loadable with identical roles.
        canonical = bank_loader.load_problem("PY-C3-COUNT-DIV")
        transfer = bank_loader.load_problem("PY-C3-COUNT-DIV-TRANSFER")
        probe = bank_loader.load_problem("PY-C3-LOOP-MISCONCEPTION")
        self.assertEqual(
            (canonical.variant_role, transfer.variant_role, probe.variant_role),
            ("canonical", "transfer", "remedial"),
        )
        self.assertEqual(
            transfer.isomorphic_group_id, canonical.isomorphic_group_id
        )
        for problem in (canonical, transfer, probe):
            self.assertEqual(problem.concept_id, "C3")
            self.assertEqual(problem.language, "python")


if __name__ == "__main__":
    unittest.main()
