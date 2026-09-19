"""COGNIFY ai-service — confidence / grounding gate (Step 7).

Even a schema-valid LLM diagnosis is rejected (→ deterministic fallback)
when it is not trustworthy:

- confidence below ``MIN_ACCEPT_CONFIDENCE`` (default 0.50), or
- ungrounded: for a failed execution it cites none of the decisive
  failure evidence (failed test, expected/actual output, stdout/stderr,
  code), or it cites only candidate/history/recurring labels with no
  observable failure link.

The gate is pure and deterministic: same (diagnosis, pack) always yields
the same verdict. No database, no mastery, no hints, no adaptive logic.
"""
from __future__ import annotations

from typing import Any

from packages.evidence.models import EvidencePack

from .models import Diagnosis

MIN_ACCEPT_CONFIDENCE: float = 0.50

# Refs that directly ground a diagnosis in the observed failure.
_FAILURE_GROUNDED_BARE: frozenset[str] = frozenset(
    {"code", "stdout", "stderr", "expected_output", "actual_output"}
)


def _is_failure_grounded(diagnosis: Diagnosis, pack: EvidencePack) -> bool:
    if pack.failed_count == 0:
        return True  # nothing to ground against; validator already checked refs
    for ref in diagnosis.evidence_refs:
        if ref in _FAILURE_GROUNDED_BARE:
            return True
        if ref.startswith("failed_test:") or ref.startswith("test:"):
            return True
    return False


def confidence_grounding_gate(
    diagnosis: Diagnosis,
    pack: EvidencePack | dict[str, Any],
    *,
    min_confidence: float = MIN_ACCEPT_CONFIDENCE,
) -> tuple[bool, str]:
    """Apply the acceptance gate to a validated diagnosis.

    Returns:
        ``(accepted, reason)`` — ``reason`` is human-readable and
        deterministic (used in logs and to explain fallback).
    """
    if isinstance(pack, dict):
        pack = EvidencePack.from_dict(pack)
    if not isinstance(pack, EvidencePack):
        return False, "invalid EvidencePack for gating."
    if not isinstance(diagnosis, Diagnosis):
        return False, "invalid diagnosis shape for gating."
    if not 0.0 <= float(diagnosis.confidence) <= 1.0:
        return False, f"confidence {diagnosis.confidence!r} out of range [0, 1]."
    if float(diagnosis.confidence) < float(min_confidence):
        return (
            False,
            f"confidence {float(diagnosis.confidence):.2f} below "
            f"minimum {float(min_confidence):.2f}.",
        )
    if not _is_failure_grounded(diagnosis, pack):
        return (
            False,
            "evidence_refs lack failure grounding: cite the decisive failed "
            "test or observed output (failed_test:<id>, expected_output, "
            "actual_output, stdout, stderr, or code).",
        )
    return True, "accepted: confidence and grounding checks passed."


__all__ = [
    "MIN_ACCEPT_CONFIDENCE",
    "confidence_grounding_gate",
]
