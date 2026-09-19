"""COGNIFY verification — deterministic reason builder (Step 10).

Pure string builders so every ``VerificationResult`` explains WHY it holds.
No DB, no LLM, no randomness, no clock. Each message is a deterministic
function of its inputs and stays within the 10..500 char result bound.

Wording contract: ``PASS + PASS`` is described as "verified improvement
for this intervention/concept instance" — never as mastery. Mastery
remains owned by Step 8 (Learner Model); verification only produces
evidence.
"""

from __future__ import annotations

from .models import ReasonCode


def original_retry_missing_reason(
    original_problem_id: str, transfer_problem_id: str | None = None
) -> str:
    transfer_bit = (
        f" Transfer problem {transfer_problem_id} is also awaiting a result."
        if transfer_problem_id is not None
        else " No transfer result can be interpreted yet either."
    )
    return (
        f"Original retry on {original_problem_id} has no result yet; "
        f"verification is INCOMPLETE (not ready).{transfer_bit} "
        "No improvement is inferred without the original retry."
    )


def original_retry_failed_reason(
    original_problem_id: str,
    original_outcome: str,
    transfer_problem_id: str | None = None,
) -> str:
    transfer_bit = (
        f" Transfer problem {transfer_problem_id} does not change the verdict."
        if transfer_problem_id is not None
        else ""
    )
    return (
        f"Original retry on {original_problem_id} ended as {original_outcome} "
        f"(not PASS); outcome NOT_IMPROVED.{transfer_bit} Verified improvement "
        "requires PASS on the original retry first."
    )


def original_passed_transfer_missing_reason(
    original_problem_id: str, transfer_problem_id: str | None = None
) -> str:
    transfer_bit = (
        f" Transfer problem {transfer_problem_id} has no result yet."
        if transfer_problem_id is not None
        else " No transfer problem result is available yet."
    )
    return (
        f"Original retry on {original_problem_id} passed, but{transfer_bit} "
        " Verification is INCOMPLETE (not ready): PASS plus PASS is required "
        "for VERIFIED_IMPROVED, and improvement is never inferred from a "
        "single retry."
    )


def original_passed_transfer_failed_reason(
    original_problem_id: str, transfer_problem_id: str, transfer_outcome: str
) -> str:
    return (
        f"Original retry on {original_problem_id} passed, but transfer problem "
        f"{transfer_problem_id} ended as {transfer_outcome} (not PASS); outcome "
        "SURFACE_FIX. The original fix did not generalize to the unseen "
        "problem, so this is evidence for this intervention instance only, "
        "not mastery."
    )


def original_and_transfer_passed_reason(
    original_problem_id: str, transfer_problem_id: str
) -> str:
    return (
        f"Original retry on {original_problem_id} passed and transfer problem "
        f"{transfer_problem_id} passed; outcome VERIFIED_IMPROVED for this "
        "intervention/concept instance. This is verified-improvement evidence, "
        "not concept mastery (mastery remains owned by Step 8)."
    )


def build_reason(
    reason_code: ReasonCode | str,
    *,
    original_problem_id: str,
    transfer_problem_id: str | None = None,
    original_outcome: str | None = None,
    transfer_outcome: str | None = None,
) -> str:
    """Build the deterministic explanation for ``reason_code``.

    Args:
        reason_code: which branch of the decision table was taken
            (``ReasonCode`` or its case/space-tolerant name).
        original_problem_id: the retried problem id (for the message).
        transfer_problem_id: the transfer problem id, if known.
        original_outcome: terminal original outcome name, if any.
        transfer_outcome: terminal transfer outcome name, if any.

    Raises:
        TypeError / ValueError: on unknown codes or missing fields needed
            by the selected template.
    """
    from .models import normalize_reason_code

    code = normalize_reason_code(reason_code)
    if not isinstance(original_problem_id, str) or not original_problem_id.strip():
        raise ValueError("original_problem_id must be a non-empty string.")
    original_pid = original_problem_id.strip()

    if code is ReasonCode.ORIGINAL_RETRY_MISSING:
        return original_retry_missing_reason(original_pid, transfer_problem_id)
    if code is ReasonCode.ORIGINAL_RETRY_FAILED:
        if original_outcome is None:
            raise ValueError(
                "original_outcome is required for ORIGINAL_RETRY_FAILED."
            )
        return original_retry_failed_reason(
            original_pid, str(original_outcome).strip().upper(), transfer_problem_id
        )
    if code is ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_MISSING:
        return original_passed_transfer_missing_reason(
            original_pid, transfer_problem_id
        )
    if code is ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_FAILED:
        if transfer_problem_id is None:
            raise ValueError(
                "transfer_problem_id is required for "
                "ORIGINAL_RETRY_PASSED_TRANSFER_FAILED."
            )
        if transfer_outcome is None:
            raise ValueError(
                "transfer_outcome is required for "
                "ORIGINAL_RETRY_PASSED_TRANSFER_FAILED."
            )
        return original_passed_transfer_failed_reason(
            original_pid,
            transfer_problem_id.strip(),
            str(transfer_outcome).strip().upper(),
        )
    # ORIGINAL_AND_TRANSFER_PASSED
    if transfer_problem_id is None:
        raise ValueError(
            "transfer_problem_id is required for ORIGINAL_AND_TRANSFER_PASSED."
        )
    return original_and_transfer_passed_reason(
        original_pid, transfer_problem_id.strip()
    )


__all__ = [
    "build_reason",
    "original_and_transfer_passed_reason",
    "original_passed_transfer_failed_reason",
    "original_passed_transfer_missing_reason",
    "original_retry_failed_reason",
    "original_retry_missing_reason",
]
