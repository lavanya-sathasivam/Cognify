"""COGNIFY ai-service — structured output validator (Step 7).

Validates the COMPLETE LLM response against a strict schema AND grounds
every ID/reference in the EvidencePack that produced the prompt:

- Exactly the keys {concept_id, misconception_id, confidence,
  explanation, evidence_refs} (missing or extra keys rejected).
- concept_id must equal the pack's concept (case/space tolerant, stored UPPER).
- misconception_id must be one of the pack's candidates (taxonomy-checked
  and belonging to the pack concept). Hallucinated IDs rejected.
- confidence must be a number in [0, 1] (bool rejected).
- explanation must be concise (10..500 chars after stripping).
- evidence_refs must be 1..8 unique non-empty strings in the allowed
  reference language; every test/candidate ID mentioned must exist in
  the pack.

Raises :class:`DiagnosisValidationError` on any violation. No database,
no mastery, no hints, no adaptive logic here.
"""
from __future__ import annotations

from typing import Any

from packages.evidence.models import EvidencePack
from packages.taxonomy import is_valid_misconception, misconception_belongs_to

from .models import (
    MAX_EVIDENCE_REFS,
    MAX_EVIDENCE_REF_CHARS,
    MAX_EXPLANATION_CHARS,
    MIN_EVIDENCE_REFS,
    MIN_EXPLANATION_CHARS,
    Diagnosis,
)

REQUIRED_KEYS: tuple[str, ...] = (
    "concept_id",
    "misconception_id",
    "confidence",
    "explanation",
    "evidence_refs",
)

# Bare section refs that need no ID.
_BARE_REFS: frozenset[str] = frozenset(
    {
        "code",
        "execution_status",
        "stdout",
        "stderr",
        "expected_output",
        "actual_output",
        "concept_history",
        "recent_events",
    }
)

# Prefixed refs of the form "<kind>:<value>".
_PREFIXED_KINDS: frozenset[str] = frozenset(
    {"failed_test", "test", "candidate", "history", "recurring"}
)


class DiagnosisValidationError(ValueError):
    """The LLM response failed strict schema or grounding validation."""


def _norm(raw: object) -> str:
    if not isinstance(raw, str):
        raise DiagnosisValidationError(f"Expected str, got {type(raw).__name__}.")
    text = raw.strip()
    if not text:
        raise DiagnosisValidationError("String value must be non-empty.")
    return text


def _check_evidence_ref(ref: str, pack: EvidencePack) -> str:
    text = ref.strip()
    if not text:
        raise DiagnosisValidationError("evidence_refs entries must be non-empty.")
    if len(text) > MAX_EVIDENCE_REF_CHARS:
        raise DiagnosisValidationError(f"evidence_ref too long: {text!r}.")
    if text in _BARE_REFS:
        return text
    if ":" not in text:
        raise DiagnosisValidationError(
            f"Unknown evidence ref {text!r}. Use a bare section name or '<kind>:<id>'."
        )
    kind, _, value = text.partition(":")
    kind = kind.strip()
    value = value.strip()
    if kind not in _PREFIXED_KINDS or not value:
        raise DiagnosisValidationError(
            f"Unknown evidence ref {text!r}. Allowed kinds: {sorted(_PREFIXED_KINDS)}."
        )
    if kind in ("failed_test", "test"):
        valid_ids = {t.test_id for t in pack.failed_tests}
        if value not in valid_ids:
            raise DiagnosisValidationError(
                f"evidence ref {text!r} is hallucinated: "
                f"unknown failed test (pack has {sorted(valid_ids)!r})."
            )
        return f"{kind}:{value}"
    # candidate / history / recurring all reference misconception candidates.
    candidate_ids = {c.misconception_id for c in pack.misconception_candidates}
    norm = value.strip().upper()
    if norm not in candidate_ids:
        raise DiagnosisValidationError(
            f"evidence ref {text!r} is hallucinated: "
            f"{norm!r} is not a pack candidate {sorted(candidate_ids)!r}."
        )
    return f"{kind}:{norm}"


def validate_llm_diagnosis(
    payload: Any, pack: EvidencePack | dict[str, Any]
) -> Diagnosis:
    """Validate a raw LLM JSON payload against the pack (strict).

    Args:
        payload: decoded JSON value from the LLM (must be a dict with
            exactly the five diagnosis keys).
        pack: EvidencePack (or dict) the prompt was built from.

    Returns:
        Validated :class:`Diagnosis` (IDs normalized to UPPER).

    Raises:
        DiagnosisValidationError: on any schema or grounding violation.
    """
    if isinstance(pack, dict):
        try:
            pack = EvidencePack.from_dict(pack)
        except Exception as exc:
            raise DiagnosisValidationError(f"Invalid EvidencePack: {exc}.") from exc
    if not isinstance(pack, EvidencePack):
        raise DiagnosisValidationError(
            f"pack must be EvidencePack or dict, got {type(pack).__name__}."
        )
    if not isinstance(payload, dict):
        raise DiagnosisValidationError(
            f"LLM response must be a JSON object, got {type(payload).__name__}."
        )
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise DiagnosisValidationError(f"LLM response missing keys: {missing}.")
    extra = [k for k in payload if k not in REQUIRED_KEYS]
    if extra:
        raise DiagnosisValidationError(f"LLM response has extra keys: {extra}.")

    # concept_id must match the pack concept.
    raw_concept = payload["concept_id"]
    if not isinstance(raw_concept, str):
        raise DiagnosisValidationError("concept_id must be str.")
    concept = raw_concept.strip().upper()
    if concept != pack.concept_id:
        raise DiagnosisValidationError(
            f"concept_id {concept!r} does not match pack concept {pack.concept_id!r}."
        )

    # misconception_id must be a pack candidate (taxonomy + belonging).
    raw_m = payload["misconception_id"]
    if not isinstance(raw_m, str):
        raise DiagnosisValidationError("misconception_id must be str.")
    mid = raw_m.strip().upper()
    candidate_ids = {c.misconception_id for c in pack.misconception_candidates}
    if mid not in candidate_ids:
        raise DiagnosisValidationError(
            f"misconception_id {mid!r} is hallucinated: "
            f"not in pack candidates {sorted(candidate_ids)!r}."
        )
    if not is_valid_misconception(mid) or not misconception_belongs_to(mid, concept):
        raise DiagnosisValidationError(
            f"misconception_id {mid!r} is invalid for concept {concept!r}."
        )

    # confidence 0..1 (bool rejected).
    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise DiagnosisValidationError("confidence must be a number in [0, 1].")
    confidence_f = float(confidence)
    if not 0.0 <= confidence_f <= 1.0:
        raise DiagnosisValidationError(
            f"confidence must be in [0, 1], got {payload['confidence']!r}."
        )

    # explanation concise.
    explanation = payload["explanation"]
    if not isinstance(explanation, str):
        raise DiagnosisValidationError("explanation must be str.")
    explanation = explanation.strip()
    if not MIN_EXPLANATION_CHARS <= len(explanation) <= MAX_EXPLANATION_CHARS:
        raise DiagnosisValidationError(
            f"explanation must be {MIN_EXPLANATION_CHARS}..{MAX_EXPLANATION_CHARS} "
            f"chars, got {len(explanation)}."
        )

    # evidence_refs: shape + grounding of every entry.
    refs = payload["evidence_refs"]
    if not isinstance(refs, (list, tuple)):
        raise DiagnosisValidationError("evidence_refs must be a list of str.")
    refs = list(refs)
    if not MIN_EVIDENCE_REFS <= len(refs) <= MAX_EVIDENCE_REFS:
        raise DiagnosisValidationError(
            f"evidence_refs must hold {MIN_EVIDENCE_REFS}..{MAX_EVIDENCE_REFS} "
            f"entries, got {len(refs)}."
        )
    grounded: list[str] = []
    for item in refs:
        if not isinstance(item, str):
            raise DiagnosisValidationError("evidence_refs entries must be str.")
        grounded.append(_check_evidence_ref(item, pack))
    if len(set(grounded)) != len(grounded):
        raise DiagnosisValidationError(f"evidence_refs contains duplicates: {refs!r}.")

    return Diagnosis(
        concept_id=concept,
        misconception_id=mid,
        confidence=confidence_f,
        explanation=explanation,
        evidence_refs=grounded,
    )


__all__ = [
    "REQUIRED_KEYS",
    "DiagnosisValidationError",
    "validate_llm_diagnosis",
]
