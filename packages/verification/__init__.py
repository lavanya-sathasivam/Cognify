"""COGNIFY verification package (Step 10: Deterministic Verification Engine).

Pure, deterministic, stdlib-only: decides whether a student's improvement
after an intervention is genuine from two already-produced attempt results
(original retry + transfer/isomorphic problem). No DB writes, no LLM
calls, no frontend, no code execution, no mastery calculation, no adaptive
ranking.

Typical use::

    from packages.verification import (
        VerificationAttempt, VerificationContext, verify_improvement,
    )
    context = VerificationContext(
        original_problem_id="PY-C3-001",
        transfer_problem_id="PY-C3-002",
        concept_id="C3",
        language_track="python",
        target_misconception_id="C3-M01",
        intervention_level="hint-L2",
        original_retry=VerificationAttempt(
            problem_id="PY-C3-001", concept_id="C3",
            language_track="python", outcome="PASS",
        ),
        transfer=VerificationAttempt(
            problem_id="PY-C3-002", concept_id="C3",
            language_track="python", outcome="PASS", is_transfer=True,
        ),
        isomorphic_group_id="ISO-C3-01",
    )
    result = verify_improvement(context)
    result.outcome  # VerificationOutcome.VERIFIED_IMPROVED

Ownership: ``PASS + PASS`` means "verified improvement for this
intervention/concept instance" — never "the student mastered the concept".
Mastery remains owned by Step 8 (Learner Model / ``learner_engine``), which
may later consume ``result.outcome`` / ``result.concept_id`` /
``result.target_misconception_id`` / ``result.original_passed`` /
``result.transfer_passed`` / ``result.evidence`` (see
``engine.to_learner_evidence``). This package never imports service code
and never modifies ``learner_engine``.
"""

from __future__ import annotations

from .engine import build_evidence, to_learner_evidence, verify_improvement
from .models import (
    NOT_READY_ALIAS,
    VALID_EXECUTION_OUTCOMES,
    VALID_REASON_CODES,
    VALID_VERIFICATION_OUTCOMES,
    ExecutionOutcome,
    ReasonCode,
    VerificationAttempt,
    VerificationContext,
    VerificationOutcome,
    VerificationResult,
    is_pass,
    normalize_concept_id,
    normalize_execution_outcome,
    normalize_language_track,
    normalize_misconception_id,
    normalize_reason_code,
    normalize_verification_outcome,
)
from .reasons import build_reason

__all__ = [
    "NOT_READY_ALIAS",
    "VALID_EXECUTION_OUTCOMES",
    "VALID_REASON_CODES",
    "VALID_VERIFICATION_OUTCOMES",
    "ExecutionOutcome",
    "ReasonCode",
    "VerificationAttempt",
    "VerificationContext",
    "VerificationOutcome",
    "VerificationResult",
    "build_evidence",
    "build_reason",
    "is_pass",
    "normalize_concept_id",
    "normalize_execution_outcome",
    "normalize_language_track",
    "normalize_misconception_id",
    "normalize_reason_code",
    "normalize_verification_outcome",
    "to_learner_evidence",
    "verify_improvement",
]
