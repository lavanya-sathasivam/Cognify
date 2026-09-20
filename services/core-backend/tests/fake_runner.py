"""Shared scripted execution fake for core-backend API tests (Step 16/17).

Marker-dispatched runner (no Docker, no host execution of student code):

- code containing ``RANGE_BUG`` reproduces the Step 14 off-by-one on the
  canonical problem via an INDEPENDENT reimplementation;
- ``TRANSFER_BUG`` fails the transfer problem;
- ``CRASH`` / ``HANG`` markers produce runtime-error / timeout outcomes;
- anything else passes honestly against the bank's own expected outputs.

Test-only helper: never importable by production code paths, never a
production execution mode.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.problem_bank import loader as bank_loader

CANONICAL_ID = "PY-C3-COUNT-DIV"
TRANSFER_ID = "PY-C3-COUNT-DIV-TRANSFER"

WRONG_CODE = (
    "RANGE_BUG\n"
    "def count_divisible(nums, k):\n"
    '    """Return how many numbers in nums are divisible by k."""\n'
    "    count = 0\n"
    "    for i in range(len(nums) - 1):\n"
    "        if nums[i] % k == 0:\n"
    "            count += 1\n"
    "    return count\n"
)

FIXED_CODE = (
    "def count_divisible(nums, k):\n"
    '    """Return how many numbers in nums are divisible by k."""\n'
    "    count = 0\n"
    "    for x in nums:\n"
    "        if x % k == 0:\n"
    "            count += 1\n"
    "    return count\n"
)

TRANSFER_CODE = (
    "def count_cold_days(temps, threshold):\n"
    '    """Return how many temperatures are strictly below threshold."""\n'
    "    count = 0\n"
    "    for t in temps:\n"
    "        if t < threshold:\n"
    "            count += 1\n"
    "    return count\n"
)


def buggy_canonical_output(stdin_data: str) -> str:
    """Independent reimplementation of the off-by-one under test."""
    parts = stdin_data.strip().split()
    n, k = int(parts[0]), int(parts[1])
    nums = list(map(int, parts[2:2 + n]))
    count = 0
    for i in range(len(nums) - 1):
        if nums[i] % k == 0:
            count += 1
    return str(count) + "\n"


class MarkerRunner:
    """Fake runner dispatching on code markers (never runs student code)."""

    language = "python"

    def __init__(self) -> None:
        canonical = bank_loader.load_problem(CANONICAL_ID)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        self._canonical = {c.input: c.expected_output for c in canonical.all_tests()}
        self._transfer = {c.input: c.expected_output for c in transfer.all_tests()}

    def compile(self, code: str, timeout_seconds: float) -> None:
        return None

    def run_single(self, code: str, stdin_data: str, timeout_seconds: float):
        if "HANG" in code:
            return SimpleNamespace(
                stdout="", stderr="", exit_code=0, timed_out=True, time_ms=5000
            )
        if "CRASH" in code:
            return SimpleNamespace(
                stdout="",
                stderr="Traceback (most recent call last): ZeroDivisionError\n",
                exit_code=1,
                timed_out=False,
                time_ms=5,
            )
        if "RANGE_BUG" in code and stdin_data in self._canonical:
            return SimpleNamespace(
                stdout=buggy_canonical_output(stdin_data),
                stderr="",
                exit_code=0,
                timed_out=False,
                time_ms=5,
            )
        if "TRANSFER_BUG" in code and stdin_data in self._transfer:
            return SimpleNamespace(
                stdout="9999\n", stderr="", exit_code=0, timed_out=False, time_ms=5
            )
        expected = self._canonical.get(stdin_data, self._transfer.get(stdin_data))
        return SimpleNamespace(
            stdout=expected + "\n", stderr="", exit_code=0, timed_out=False, time_ms=5
        )


def make_client():
    """TestClient for the student app wired to the marker runner."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(
        create_app(runner_factory=lambda lang, timeout: MarkerRunner())
    )


__all__ = [
    "CANONICAL_ID",
    "FIXED_CODE",
    "TRANSFER_CODE",
    "TRANSFER_ID",
    "WRONG_CODE",
    "MarkerRunner",
    "buggy_canonical_output",
    "make_client",
]
