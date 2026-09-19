"""COGNIFY evidence — example EvidencePack (data only, never executed).

Built deterministically with ``build_evidence_pack`` from:
- ``EXAMPLE_PYTHON_PROBLEM`` (PY-C3-001, concept C3),
- a canned wrong-output ExecutionResult dict (off-by-one: last even missed),
- a canned LearnerSnapshot (prior C3 attempts, recurring C3-M01 flag).

The example shows every required evidence section populated while carrying
no secrets, no full history, and no confirmed misconception.
"""
from __future__ import annotations

from typing import Any

from packages.problem_schema.examples import EXAMPLE_PYTHON_PROBLEM

from .builder import build_evidence_pack
from .models import (
    ConceptStateSnapshot,
    CounterSnapshot,
    EvidencePack,
    EventSnapshot,
    FlagSnapshot,
    LearnerSnapshot,
)

# A plausible buggy submission: range excludes n (off-by-one) — data only.
EXAMPLE_SUBMISSION_CODE: str = (
    "def sum_evens(n: int) -> int:\n"
    "    total = 0\n"
    "    for i in range(1, n):\n"
    "        if i % 2 == 0:\n"
    "            total += i\n"
    "    return total\n"
)

# Canned execution result dict (same shape as ExecutionResult.to_dict()).
# Raw strings are preserved verbatim by the builder.
EXAMPLE_EXECUTION_RESULT: dict[str, Any] = {
    "status": "FAILED",
    "language": "python",
    "execution_time_ms": 79,
    "stdout": "6\n",
    "stderr": "",
    "tests": [
        {
            "test_id": "P1",
            "passed": False,
            "input": "10",
            "expected_output": "30",
            "actual_output": "6\n",
            "stdout": "6\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "time_ms": 38,
        },
        {
            "test_id": "P2",
            "passed": True,
            "input": "1",
            "expected_output": "0",
            "actual_output": "0\n",
            "stdout": "0\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "time_ms": 41,
        },
    ],
    "passed_count": 1,
    "failed_count": 1,
    "failed_test_id": "P1",
    "expected_output": "30",
    "actual_output": "6\n",
}

EXAMPLE_LEARNER_SNAPSHOT: LearnerSnapshot = LearnerSnapshot(
    user_id=7,
    journey_id=12,
    language_track="python",
    concept_state=ConceptStateSnapshot(
        concept_id="C3",
        stored_mastery=0.35,
        attempt_count=5,
        successful_attempts=2,
        current_band="developing",
        trend="stable",
        hint_count=1,
        transfer_attempts=1,
        transfer_successes=0,
    ),
    counters=(
        CounterSnapshot(
            concept_id="C3",
            misconception_id="C3-M01",
            occurrence_count=3,
            active=True,
            last_seen_at="2026-09-10T12:00:00",
        ),
        CounterSnapshot(
            concept_id="C3",
            misconception_id="C3-M04",
            occurrence_count=1,
            active=True,
            last_seen_at="2026-09-12T09:30:00",
        ),
    ),
    flags=(
        FlagSnapshot(
            concept_id="C3",
            misconception_id="C3-M01",
            is_recurring=True,
            reason="3 prior occurrences of off-by-one bounds",
        ),
        FlagSnapshot(
            concept_id="C3",
            misconception_id="C3-M04",
            is_recurring=False,
            reason=None,
        ),
    ),
    events=(
        EventSnapshot(
            event_type="attempt",
            concept_id="C3",
            misconception_id=None,
            created_at="2026-09-12T09:30:00",
            metadata={"problem_id": "PY-C3-001", "success": False},
        ),
        EventSnapshot(
            event_type="hint",
            concept_id="C3",
            misconception_id="C3-M01",
            created_at="2026-09-12T09:35:00",
            metadata={"problem_id": "PY-C3-001", "hint_level": 1},
        ),
    ),
)


def make_example_evidence_pack() -> EvidencePack:
    """Build a fresh copy of the example pack (deterministic)."""
    return build_evidence_pack(
        code=EXAMPLE_SUBMISSION_CODE,
        problem=EXAMPLE_PYTHON_PROBLEM,
        execution_result=EXAMPLE_EXECUTION_RESULT,
        learner_snapshot=EXAMPLE_LEARNER_SNAPSHOT,
    )


EXAMPLE_EVIDENCE_PACK: EvidencePack = make_example_evidence_pack()

EXAMPLE_EVIDENCE_DICT: dict[str, Any] = EXAMPLE_EVIDENCE_PACK.to_dict()

__all__ = [
    "EXAMPLE_EVIDENCE_DICT",
    "EXAMPLE_EVIDENCE_PACK",
    "EXAMPLE_EXECUTION_RESULT",
    "EXAMPLE_LEARNER_SNAPSHOT",
    "EXAMPLE_SUBMISSION_CODE",
    "make_example_evidence_pack",
]
