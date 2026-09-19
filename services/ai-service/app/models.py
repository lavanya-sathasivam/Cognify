"""COGNIFY ai-service — diagnosis request/response models (Step 7).

Scope: data shapes for AI diagnosis ONLY.

- Input is an EvidencePack (observed evidence, never a DB session).
- Output is a Diagnosis: concept_id + misconception_id + confidence
  (0-1) + concise explanation + supporting evidence references.
- This module performs shape validation only. Grounding against a
  specific EvidencePack (candidate membership, concept match, evidence
  references) lives in ``validator.py`` / ``gate.py``.

NOT implemented here: LLM calls, prompt building, mastery calculation,
hint generation, adaptive decisions, database access. No network, no
filesystem, no environment reads, no DB imports.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MAX_EXPLANATION_CHARS: int = 500
MIN_EXPLANATION_CHARS: int = 10
MAX_EVIDENCE_REFS: int = 8
MIN_EVIDENCE_REFS: int = 1
MAX_EVIDENCE_REF_CHARS: int = 200

DiagnosisSource = Literal["llm", "fallback"]


def _norm_id(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str.")
    text = value.strip().upper()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


class Diagnosis(BaseModel):
    """Validated diagnosis shape (LLM output or fallback output).

    Strict: exactly these five fields. Extra fields are forbidden so
    hallucinated payloads cannot smuggle unvalidated content through.
    """

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    concept_id: str
    misconception_id: str
    confidence: float
    explanation: str
    evidence_refs: list[str] = Field(min_length=MIN_EVIDENCE_REFS, max_length=MAX_EVIDENCE_REFS)

    @field_validator("concept_id")
    @classmethod
    def _norm_concept(cls, value: object) -> str:
        return _norm_id(value, "concept_id")

    @field_validator("misconception_id")
    @classmethod
    def _norm_misconception(cls, value: object) -> str:
        return _norm_id(value, "misconception_id")

    @field_validator("confidence", mode="before")
    @classmethod
    def _check_confidence(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("confidence must be a number in [0, 1].")
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {value!r}.")
        return number

    @field_validator("explanation")
    @classmethod
    def _check_explanation(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("explanation must be str.")
        text = value.strip()
        if not (MIN_EXPLANATION_CHARS <= len(text) <= MAX_EXPLANATION_CHARS):
            raise ValueError(
                f"explanation must be {MIN_EXPLANATION_CHARS}..{MAX_EXPLANATION_CHARS} "
                f"chars (concise), got {len(text)}."
            )
        return text

    @field_validator("evidence_refs")
    @classmethod
    def _check_refs(cls, value: object) -> list[str]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("evidence_refs must be a list of str.")
        refs: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("evidence_refs entries must be str.")
            text = item.strip()
            if not text:
                raise ValueError("evidence_refs entries must be non-empty.")
            if len(text) > MAX_EVIDENCE_REF_CHARS:
                raise ValueError(
                    f"evidence_ref exceeds {MAX_EVIDENCE_REF_CHARS} chars: {text!r}."
                )
            refs.append(text)
        if not (MIN_EVIDENCE_REFS <= len(refs) <= MAX_EVIDENCE_REFS):
            raise ValueError(
                f"evidence_refs must hold {MIN_EVIDENCE_REFS}..{MAX_EVIDENCE_REFS} "
                f"entries, got {len(refs)}."
            )
        if len(set(refs)) != len(refs):
            raise ValueError(f"evidence_refs contains duplicates: {refs!r}.")
        return refs

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DiagnosisResult(BaseModel):
    """Service-level diagnosis result: the diagnosis plus its source.

    ``source`` is ``"llm"`` when a grounded LLM diagnosis passed the
    validator and gate, else ``"fallback"`` (deterministic classifier).
    """

    model_config = {"extra": "forbid"}

    concept_id: str
    misconception_id: str
    confidence: float
    explanation: str
    evidence_refs: list[str]
    source: DiagnosisSource

    @field_validator("concept_id")
    @classmethod
    def _norm_concept(cls, value: object) -> str:
        return _norm_id(value, "concept_id")

    @field_validator("misconception_id")
    @classmethod
    def _norm_misconception(cls, value: object) -> str:
        return _norm_id(value, "misconception_id")

    @field_validator("confidence", mode="before")
    @classmethod
    def _check_confidence(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("confidence must be a number in [0, 1].")
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {value!r}.")
        return number

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DiagnosisRequest(BaseModel):
    """API request body: a raw EvidencePack mapping (validated downstream).

    The mapping is kept as a plain dict here so the endpoint can convert
    it with ``EvidencePack.from_dict`` (single source of truth for pack
    validation) and return 422 on any malformed pack.
    """

    model_config = {"extra": "forbid"}

    evidence_pack: dict[str, Any]


__all__ = [
    "MAX_EVIDENCE_REFS",
    "MAX_EVIDENCE_REF_CHARS",
    "MAX_EXPLANATION_CHARS",
    "MIN_EVIDENCE_REFS",
    "MIN_EXPLANATION_CHARS",
    "Diagnosis",
    "DiagnosisRequest",
    "DiagnosisResult",
    "DiagnosisSource",
]
