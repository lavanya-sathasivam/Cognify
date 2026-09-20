"""COGNIFY ai-service — diagnosis orchestrator (Steps 7 + 15).

``diagnose_pack`` is the single entry point for AI diagnosis:

1. Try the deterministic Step 15 evidence rules on the EvidencePack
   FIRST (pure, no LLM, no database). A rule fires only when several
   independent evidence signals corroborate one candidate misconception;
   the hit is re-validated with the strict validator + gate.
2. Otherwise build the LLM prompt from the EvidencePack ONLY (no DB
   access — the signature accepts just ``pack`` + ``client``).
3. Ask the LLM (if configured) for one strict JSON object.
4. Parse + strictly validate the complete response (reject hallucinated
   IDs, wrong concept, bad confidence, ungrounded refs).
5. Apply the confidence/grounding gate.
6. On ANY failure (no rule hit; LLM unavailable, malformed, invalid,
   gated) return the deterministic fallback classifier.

Rule diagnoses are deterministic non-LLM output, so they are reported
with ``source="fallback"`` (the existing Step 7 contract keeps exactly
two sources: ``"llm"`` vs deterministic). A rule hit is observable via
its ``"Rule <RULE_ID>:"`` explanation prefix and higher confidence; the
generic fallback never carries a rule prefix.

The service never updates a database, never calculates mastery, never
generates hints, and never makes adaptive/roadmap decisions. It returns
a diagnosis; callers own everything downstream.
"""
from __future__ import annotations

import json
from typing import Any

from packages.evidence.models import EvidencePack

from .fallback import fallback_diagnose
from .gate import MIN_ACCEPT_CONFIDENCE, confidence_grounding_gate
from .llm_client import BaseLLMClient
from .models import Diagnosis, DiagnosisResult
from .prompt import build_diagnosis_prompt
from .rules import try_rule_diagnosis
from .validator import DiagnosisValidationError, validate_llm_diagnosis


def _parse_llm_json(raw: str) -> Any:
    if not isinstance(raw, str) or not raw.strip():
        raise DiagnosisValidationError("LLM returned empty text.")
    text = raw.strip()
    # Tolerate markdown fences around the JSON object (still strict inside).
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence (``` or ```json) and trailing fence.
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiagnosisValidationError(f"LLM response is not valid JSON: {exc}.") from exc


def diagnose_pack(
    pack: EvidencePack | dict[str, Any],
    client: BaseLLMClient | None,
    *,
    min_confidence: float = MIN_ACCEPT_CONFIDENCE,
) -> DiagnosisResult:
    """Diagnose one EvidencePack via LLM with deterministic fallback.

    Args:
        pack: EvidencePack (or dict). The ONLY data the LLM sees.
        client: LLM client or None (None → fallback immediately).
        min_confidence: gate threshold for LLM diagnoses.

    Returns:
        DiagnosisResult with ``source`` set to ``"llm"`` or ``"fallback"``.
        Deterministic Step 15 rule hits are reported as ``"fallback"``
        (non-LLM output); see the module docstring.
    """
    evidence = pack if isinstance(pack, EvidencePack) else EvidencePack.from_dict(pack)
    rule_hit = try_rule_diagnosis(evidence)
    if rule_hit is not None:
        return DiagnosisResult(
            concept_id=rule_hit.concept_id,
            misconception_id=rule_hit.misconception_id,
            confidence=rule_hit.confidence,
            explanation=rule_hit.explanation,
            evidence_refs=rule_hit.evidence_refs,
            source="fallback",
        )
    if client is None:
        fallback = fallback_diagnose(evidence)
        return DiagnosisResult(
            concept_id=fallback.concept_id,
            misconception_id=fallback.misconception_id,
            confidence=fallback.confidence,
            explanation=fallback.explanation,
            evidence_refs=fallback.evidence_refs,
            source="fallback",
        )
    prompt = build_diagnosis_prompt(evidence)
    try:
        raw = client.complete(system=prompt["system"], user=prompt["user"])
    except Exception:
        fallback = fallback_diagnose(evidence)
        return DiagnosisResult(
            concept_id=fallback.concept_id,
            misconception_id=fallback.misconception_id,
            confidence=fallback.confidence,
            explanation=fallback.explanation,
            evidence_refs=fallback.evidence_refs,
            source="fallback",
        )
    try:
        payload = _parse_llm_json(raw)
        diagnosis: Diagnosis = validate_llm_diagnosis(payload, evidence)
    except (DiagnosisValidationError, ValueError, TypeError, AttributeError):
        fallback = fallback_diagnose(evidence)
        return DiagnosisResult(
            concept_id=fallback.concept_id,
            misconception_id=fallback.misconception_id,
            confidence=fallback.confidence,
            explanation=fallback.explanation,
            evidence_refs=fallback.evidence_refs,
            source="fallback",
        )
    accepted, _reason = confidence_grounding_gate(
        diagnosis, evidence, min_confidence=min_confidence
    )
    if not accepted:
        fallback = fallback_diagnose(evidence)
        return DiagnosisResult(
            concept_id=fallback.concept_id,
            misconception_id=fallback.misconception_id,
            confidence=fallback.confidence,
            explanation=fallback.explanation,
            evidence_refs=fallback.evidence_refs,
            source="fallback",
        )
    return DiagnosisResult(
        concept_id=diagnosis.concept_id,
        misconception_id=diagnosis.misconception_id,
        confidence=diagnosis.confidence,
        explanation=diagnosis.explanation,
        evidence_refs=diagnosis.evidence_refs,
        source="llm",
    )


__all__ = ["diagnose_pack"]
