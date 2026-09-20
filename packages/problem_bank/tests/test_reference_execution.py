"""Phase 25: shipped reference solutions actually solve their bank tests.

Genuine gap: every existing reference check uses an independent PURE
re-implementation of each spec (test_step19) or a logic mirror
(test_step21a). Nothing ever executes the shipped
``problem-bank/<lang>/<PID>_canonical.py`` files, so JSON/reference drift
(a test edited without its solution, or vice versa) goes undetected.

This module executes ONLY the repo's own reviewed reference files in a
subprocess with a timeout — never student code, never network. Java is
excluded (no local toolchain in this environment); Java reference logic
stays covered by the mirrors in test_step21a.

Covers (§2, §5, §9):
- every Python reference file exists and passes ALL of its bank tests
  (public + hidden);
- per family, the canonical file fails at least one transfer test and
  the transfer file fails at least one canonical test, using the real
  files (transfer is genuinely not interchangeable).
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.problem_bank import loader as bank_loader  # noqa: E402

_TIMEOUT_SECONDS = 20

FAMILIES: tuple[tuple[str, str], ...] = (
    ("PY-C1-TEMP-CONVERT", "PY-C1-TEMP-CONVERT-TRANSFER"),
    ("PY-C2-GRADE-BAND", "PY-C2-GRADE-BAND-TRANSFER"),
    ("PY-C3-COUNT-DIV", "PY-C3-COUNT-DIV-TRANSFER"),
    ("PY-C4-RECT-METRICS", "PY-C4-RECT-METRICS-TRANSFER"),
    ("PY-C5-FIND-MAX", "PY-C5-FIND-MAX-TRANSFER"),
    ("PY-C6-COUNT-WORD", "PY-C6-COUNT-WORD-TRANSFER"),
    ("PY-C7-BANK-ACCOUNT", "PY-C7-BANK-ACCOUNT-TRANSFER"),
    ("PY-C8-FACTORIAL", "PY-C8-FACTORIAL-TRANSFER"),
)


def _reference_file(problem_id: str, language: str) -> Path:
    path = _ROOT / "problem-bank" / language / f"{problem_id}_canonical.py"
    assert path.is_file(), f"missing shipped reference file: {path}"
    return path


def _run_reference(reference: Path, stdin_data: str) -> str | None:
    """Run one shipped reference file; None on crash/timeout (a failure)."""
    try:
        completed = subprocess.run(
            [sys.executable, str(reference)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip().replace("\r\n", "\n")


def _python_problem_ids() -> list[str]:
    return sorted(bank_loader.load_all_problems())


class ShippedReferenceTests(unittest.TestCase):
    def test_every_python_reference_passes_its_bank_tests(self):
        for pid in _python_problem_ids():
            problem = bank_loader.load_problem(pid)
            reference = _reference_file(pid, problem.language)
            for case in problem.all_tests():
                got = _run_reference(reference, case.input)
                self.assertIsNotNone(got, f"{pid} {case.id}: crash/timeout")
                self.assertEqual(
                    got, case.expected_output.strip(), f"{pid} {case.id}"
                )

    def test_reference_files_cover_public_and_hidden(self):
        for pid in _python_problem_ids():
            problem = bank_loader.load_problem(pid)
            kinds = {t.id[0] for t in problem.all_tests()}
            self.assertIn("P", kinds, pid)
            self.assertIn("H", kinds, pid)


class FileLevelNonInterchangeabilityTests(unittest.TestCase):
    def test_canonical_file_fails_transfer_tests(self):
        for canonical_id, transfer_id in FAMILIES:
            transfer = bank_loader.load_problem(transfer_id)
            reference = _reference_file(canonical_id, "python")
            mismatches = sum(
                1
                for case in transfer.all_tests()
                if _run_reference(reference, case.input)
                != case.expected_output.strip()
            )
            self.assertGreater(
                mismatches, 0, f"{canonical_id} file solves {transfer_id}"
            )

    def test_transfer_file_fails_canonical_tests(self):
        for canonical_id, transfer_id in FAMILIES:
            canonical = bank_loader.load_problem(canonical_id)
            reference = _reference_file(transfer_id, "python")
            mismatches = sum(
                1
                for case in canonical.all_tests()
                if _run_reference(reference, case.input)
                != case.expected_output.strip()
            )
            self.assertGreater(
                mismatches, 0, f"{transfer_id} file solves {canonical_id}"
            )


if __name__ == "__main__":
    unittest.main()
