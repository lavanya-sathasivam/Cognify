"""COGNIFY verification — deterministic verification engine (Step 10).

Pure function ``verify_improvement`` maps a ``VerificationContext`` (two
already-produced attempt results plus their shared scope) to a
``VerificationResult``. No side effects: no DB writes, no LLM calls, no
code execution, no mastery calculation, no adaptive ranking, no network,
no filesystem, no environment reads, no clock, no randomness.

Decision table (nothing is inferred beyond it):

===================  ================  =================  ================
Original retry       Transfer          Outcome            Reason code
===================  ================  =================  ================
missing              missing           INCOMPLETE         ORIGINAL_RETRY_MISSING
missing              any               INCOMPLETE         ORIGINAL_RETRY_MISSING
non-PASS             any               NOT_IMPROVED       ORIGINAL_RETRY_FAILED
PASS                 missing           INCOMPLETE         ORIGINAL_RETRY_PASSED_TRANSFER_MISSING
PASS                 non-PASS          SURFACE_FIX        ORIGINAL_RETRY_PASSED_TRANSFER_FAILED
PASS                 PASS              VERIFIED_IMPROVED  ORIGINAL_AND_TRANSFER_PASSED
===================  ================  =================  ================

Only ``PASS`` counts as passing: ``FAIL`` / ``COMPILE_ERROR`` /
``RUNTIME_ERROR`` / ``TIMEOUT`` are all non-passing. Partial evidence,
confidence scores, and hint levels never influence the verdict.
"""

from __future__ import annotations

from typing import Any

from .models import (
    ExecutionOutcome,
    ReasonCode,
    VerificationAttempt,
    VerificationContext,
    VerificationOutcome,
    VerificationResult,
    is_pass,
)
from .reasons import build_reason


def _outcome_of(attempt: VerificationAttempt | None) -> ExecutionOutcome | None:
    if attempt is None:
        return None
    assert isinstance(attempt.outcome, ExecutionOutcome)
    return attempt.outcome


def build_evidence(context: VerificationContext) -> tuple[str, ...]:
    """Build the deterministic evidence list for ``context`` (pure).

    Order is fixed: scope line, original line, transfer line, target line,
    group line (when a group id is known anywhere). No timestamps, no
    randomness.
    """
    lines: list[str] = [
        f"scope concept={context.concept_id} track={context.language_track}",
        (
            f"original_retry problem={context.original_problem_id} "
            f"outcome={_outcome_of(context.original_retry).value if context.original_retry is not None else 'MISSING'} "
            f"passed={is_pass(_outcome_of(context.original_retry))}"
        ),
    ]
    if context.transfer_problem_id is not None or context.transfer is not None:
        transfer_pid = (
            context.transfer_problem_id
            if context.transfer_problem_id is not None
            else (context.transfer.problem_id if context.transfer is not None else "UNKNOWN")
        )
        lines.append(
            f"transfer problem={transfer_pid} "
            f"outcome={_outcome_of(context.transfer).value if context.transfer is not None else 'MISSING'} "
            f"passed={is_pass(_outcome_of(context.transfer))}"
        )
    else:
        lines.append("transfer problem=NONE outcome=MISSING passed=False")
    lines.append(
        f"target_misconception={context.target_misconception_id if context.target_misconception_id is not None else 'NONE'}"
    )
    group = context.isomorphic_group_id
    if group is None:
        for attempt in (context.original_retry, context.transfer):
            if attempt is not None and attempt.isomorphic_group_id is not None:
                group = attempt.isomorphic_group_id
                break
    lines.append(f"isomorphic_group={group if group is not None else 'NONE'}")
    return tuple(lines)


def verify_improvement(context: VerificationContext) -> VerificationResult:
    """Verify whether improvement after an intervention is genuine (pure).

    Args:
        context: validated ``VerificationContext`` holding the original
            retry result and the transfer result (each ``None`` when the
            result is not yet available).

    Returns:
        A frozen ``VerificationResult`` with the closed outcome, the
        deterministic reason code + explanation, ``original_passed`` /
        ``transfer_passed`` booleans, raw outcomes, and the evidence list
        that Step 8 (``learner_engine``) may later consume. The result
        explicitly states that ``PASS + PASS`` is verified improvement
        for this intervention/concept instance — never concept mastery.

    Raises:
        TypeError: if ``context`` is not a ``VerificationContext``.
    """
    if not isinstance(context, VerificationContext):
        raise TypeError(
            f"context must be VerificationContext, got {type(context).__name__}."
        )

    original_outcome = _outcome_of(context.original_retry)
    transfer_outcome = _outcome_of(context.transfer)
    original_passed = is_pass(original_outcome)
    transfer_passed = is_pass(transfer_outcome)

    if context.original_retry is None:
        outcome = VerificationOutcome.INCOMPLETE
        reason_code = ReasonCode.ORIGINAL_RETRY_MISSING
        reason = build_reason(
            reason_code,
            original_problem_id=context.original_problem_id,
            transfer_problem_id=context.transfer_problem_id,
        )
    elif not original_passed:
        assert original_outcome is not None
        outcome = VerificationOutcome.NOT_IMPROVED
        reason_code = ReasonCode.ORIGINAL_RETRY_FAILED
        reason = build_reason(
            reason_code,
            original_problem_id=context.original_problem_id,
            transfer_problem_id=context.transfer_problem_id,
            original_outcome=original_outcome.value,
        )
    elif context.transfer is None:
        outcome = VerificationOutcome.INCOMPLETE
        reason_code = ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_MISSING
        reason = build_reason(
            reason_code,
            original_problem_id=context.original_problem_id,
            transfer_problem_id=context.transfer_problem_id,
        )
    elif transfer_passed:
        assert transfer_outcome is not None
        assert context.transfer_problem_id is not None
        outcome = VerificationOutcome.VERIFIED_IMPROVED
        reason_code = ReasonCode.ORIGINAL_AND_TRANSFER_PASSED
        reason = build_reason(
            reason_code,
            original_problem_id=context.original_problem_id,
            transfer_problem_id=context.transfer_problem_id,
        )
    else:
        assert transfer_outcome is not None
        assert context.transfer_problem_id is not None
        outcome = VerificationOutcome.SURFACE_FIX
        reason_code = ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_FAILED
        reason = build_reason(
            reason_code,
            original_problem_id=context.original_problem_id,
            transfer_problem_id=context.transfer_problem_id,
            transfer_outcome=transfer_outcome.value,
        )

    evidence = build_evidence(context)

    # Resolve the effective isomorphic group: context wins when set,
    # otherwise the first attempt-supplied group (all supplied values are
    # already validated identical by VerificationContext).
    group = context.isomorphic_group_id
    if group is None:
        for attempt in (context.original_retry, context.transfer):
            if attempt is not None and attempt.isomorphic_group_id is not None:
                group = attempt.isomorphic_group_id
                break

    return VerificationResult(
        outcome=outcome,
        reason_code=reason_code,
        reason=reason,
        concept_id=context.concept_id,
        language_track=context.language_track,
        original_problem_id=context.original_problem_id,
        transfer_problem_id=context.transfer_problem_id,
        target_misconception_id=context.target_misconception_id,
        original_passed=original_passed,
        transfer_passed=transfer_passed,
        evidence=list(evidence),
        original_outcome=original_outcome,
        transfer_outcome=transfer_outcome,
        intervention_level=context.intervention_level,
        isomorphic_group_id=group,
    )


def to_learner_evidence(result: VerificationResult) -> dict[str, Any]:
    """Render the Step 8 integration slice for a ``VerificationResult``.

    Returns exactly the fields the future ``learner_engine`` integration
    needs (``outcome`` / ``concept_id`` / ``target_misconception_id`` /
    ``original_passed`` / ``transfer_passed`` / ``evidence`` plus the
    supporting ``reason_code`` / ``reason``). Pure mapping; never touches
    the database and never modifies ``learner_engine``.
    """
    if not isinstance(result, VerificationResult):
        raise TypeError(
            f"result must be VerificationResult, got {type(result).__name__}."
        )
    assert isinstance(result.outcome, VerificationOutcome)
    assert isinstance(result.reason_code, ReasonCode)
    return {
        "outcome": result.outcome.value,
        "concept_id": result.concept_id,
        "target_misconception_id": result.target_misconception_id,
        "original_passed": result.original_passed,
        "transfer_passed": result.transfer_passed,
        "evidence": list(result.evidence),
        "reason_code": result.reason_code.value,
        "reason": result.reason,
    }


__all__ = ["build_evidence", "to_learner_evidence", "verify_improvement"]
