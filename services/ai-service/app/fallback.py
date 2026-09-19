"""COGNIFY ai-service — deterministic fallback classifier (Step 7).

Used when the LLM is unavailable, returns malformed JSON, fails strict
validation, or fails the confidence/grounding gate. Pure function of the
EvidencePack: same pack always yields the same diagnosis.

Scoring (deterministic, no LLM, no randomness):

- base confidence 0.30 for every candidate;
- +0.20 if the candidate has an active recurring flag;
- +0.05 per prior occurrence, capped at +0.15 (3+ occurrences);
- PASSED executions are capped at 0.40 (no failure to explain).

Winner: highest score; ties broken by higher occurrence_count, then
recurring flag, then lexicographically smallest misconception_id.

Evidence refs are grounded deterministically: the decisive failed test
plus expected/actual output when a failure exists, else execution_status
plus code. Explanation is a concise template naming the winner.

NOT implemented here: LLM calls, mastery calculation, hint generation,
adaptive decisions, database access. Reads only the pack.
"""
from __future__ import annotations

from typing import Any

from packages.evidence.models import EvidencePack
from packages.taxonomy import get_misconception

from .models import Diagnosis

BASE_CONFIDENCE: float = 0.30
RECURRING_BONUS: float = 0.20
PER_OCCURRENCE_BONUS: float = 0.05
MAX_OCCURRENCE_BONUS: float = 0.15
PASSED_CONFIDENCE_CAP: float = 0.40
FALLBACK_CONFIDENCE_CAP: float = 0.55


def _as_pack(pack: EvidencePack | dict[str, Any]) -> EvidencePack:
    if isinstance(pack, EvidencePack):
        return pack
    if isinstance(pack, dict):
        return EvidencePack.from_dict(pack)
    raise TypeError(f"pack must be EvidencePack or dict, got {type(pack).__name__}.")


def fallback_diagnose(pack: EvidencePack | dict[str, Any]) -> Diagnosis:
    """Deterministically pick a candidate from observed history only."""
    pack = _as_pack(pack)
    candidates = list(pack.misconception_candidates)
    if not candidates:
        raise ValueError("EvidencePack has no misconception candidates.")

    occurrences = {h.misconception_id: h.occurrence_count for h in pack.misconception_history}
    recurring = {f.misconception_id: bool(f.is_recurring) for f in pack.recurring_flags}

    scored: list[tuple[float, int, int, str]] = []
    for cand in candidates:
        mid = cand.misconception_id
        count = int(occurrences.get(mid, 0))
        is_rec = bool(recurring.get(mid, False))
        score = BASE_CONFIDENCE
        if is_rec:
            score += RECURRING_BONUS
        score += min(count * PER_OCCURRENCE_BONUS, MAX_OCCURRENCE_BONUS)
        scored.append((score, count, int(is_rec), mid))

    # Highest score wins; deterministic tie-breaks.
    scored.sort(key=lambda row: (-row[0], -row[1], -row[2], row[3]))
    best_score, best_count, best_rec, best_mid = scored[0]

    confidence = min(float(best_score), FALLBACK_CONFIDENCE_CAP)
    if pack.failed_count == 0:
        confidence = min(confidence, PASSED_CONFIDENCE_CAP)
    confidence = max(0.0, min(1.0, round(confidence, 2)))

    try:
        name = get_misconception(best_mid).name
    except KeyError:
        name = best_mid

    if pack.failed_count > 0:
        first = pack.failed_tests[0] if pack.failed_tests else None
        test_bit = f"failed test {first.test_id}" if first is not None else "failed test"
        explanation = (
            f"Fallback: {best_mid} ({name}) best matches {test_bit} "
            f"for {pack.concept_id} (status {pack.execution_status}, "
            f"{best_count} prior occurrence(s){', recurring' if best_rec else ''})."
        )
        refs = [f"failed_test:{pack.failed_test_id}", "expected_output", "actual_output"]
        # Keep refs grounded even if the pack is unusual (e.g. COMPILE_ERROR
        # with no failed_tests — pack validation guarantees failed_count==0
        # then, so this branch always has a decisive test; guard anyway).
        if pack.failed_test_id is None:
            refs = ["execution_status", "stderr", "code"]
    else:
        explanation = (
            f"Fallback: {best_mid} ({name}) selected for {pack.concept_id} "
            f"with status {pack.execution_status}; no failure to explain."
        )
        refs = ["execution_status", "code"]

    # Enforce concise bound deterministically (truncate with ellipsis).
    if len(explanation) > 500:
        explanation = explanation[:497] + "..."

    return Diagnosis(
        concept_id=pack.concept_id,
        misconception_id=best_mid,
        confidence=confidence,
        explanation=explanation,
        evidence_refs=refs,
    )


__all__ = [
    "BASE_CONFIDENCE",
    "FALLBACK_CONFIDENCE_CAP",
    "MAX_OCCURRENCE_BONUS",
    "PASSED_CONFIDENCE_CAP",
    "PER_OCCURRENCE_BONUS",
    "RECURRING_BONUS",
    "fallback_diagnose",
]
