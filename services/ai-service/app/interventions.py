"""COGNIFY ai-service — deterministic intervention mapping (Step 15).

Companion to ``rules.py``: given a validated :class:`Diagnosis` and the
EvidencePack it was drawn from, build one small structured
:class:`Intervention`. This is NOT a generative engine:

- closed vocabularies only (four levels, five types, curated skills);
- pure function of ``(diagnosis, pack)`` — no clock, no randomness, no
  I/O, no environment reads, no database access, no learner-state writes;
- every object is tied to the diagnosed misconception and cites the
  pack's decisive failure facts (test id, expected vs observed output);
- templates are fixed strings filled with observed values only.

Progressive levels (existing Cognify idea, deterministic here):

- L1 NUDGE, L2 MICRO_LESSON, L3 SCAFFOLD, L4 RETEACH.

Escalation NEVER comes from the current failure alone. It comes only
from the pack's existing learner-history slice:

- recurring flag set and occurrence_count >= 3 -> L4 RETEACH;
- recurring flag set -> L3 SCAFFOLD;
- occurrence_count >= 1 (seen before, not recurring) -> L2 MICRO_LESSON;
- otherwise (first occurrence) -> L1 NUDGE.

Per-misconception mapping (only IDs the Step 15 rule layer diagnoses get
a curated type; any other taxonomy-valid pack candidate maps to a generic
but still evidence-tied TARGETED_HINT whose skill label is the taxonomy
name, so nothing arbitrary is ever produced):

- C3-M01 off-by-one-bounds -> BOUNDARY_CHECK / loop-boundary-checks;
- C3-M05 python-range-exclusivity -> TRACE_LOOP / range-stop-semantics.

NOT implemented here: LLM calls, mastery math, next-action ranking,
verification verdicts, learner-state mutation, database access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from packages.evidence.models import EvidencePack
from packages.taxonomy import get_misconception, is_valid_misconception

from .models import Diagnosis

InterventionLevel = Literal["L1", "L2", "L3", "L4"]
InterventionType = Literal[
    "MICRO_LESSON", "TARGETED_HINT", "BOUNDARY_CHECK", "TRACE_LOOP", "REMEDIAL_PROBLEM"
]

LEVEL_ORDER: tuple[str, ...] = ("L1", "L2", "L3", "L4")
LEVEL_NAMES: dict[str, str] = {
    "L1": "NUDGE",
    "L2": "MICRO_LESSON",
    "L3": "SCAFFOLD",
    "L4": "RETEACH",
}

_ALLOWED_LEVELS: frozenset[str] = frozenset({"L1", "L2", "L3", "L4"})
_ALLOWED_TYPES: frozenset[str] = frozenset(
    {"MICRO_LESSON", "TARGETED_HINT", "BOUNDARY_CHECK", "TRACE_LOOP", "REMEDIAL_PROBLEM"}
)

_RETEACH_MIN_OCCURRENCES: int = 3

_MID_C3_M01: str = "C3-M01"
_MID_C3_M05: str = "C3-M05"

# Curated (type, skill) per rule-supported misconception. Anything else
# valid falls back to ("TARGETED_HINT", <taxonomy name>) in the builder.
_CURATED: dict[str, tuple[str, str]] = {
    _MID_C3_M01: ("BOUNDARY_CHECK", "loop-boundary-checks"),
    _MID_C3_M05: ("TRACE_LOOP", "range-stop-semantics"),
}


def _norm_id(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str.")
    text = value.strip().upper()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


def _require_text(value: object, field_name: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string.")
    if len(text) > limit:
        raise ValueError(f"{field_name} exceeds {limit} characters.")
    return text


def _truncate(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


@dataclass(frozen=True)
class Intervention:
    """One structured, evidence-tied intervention (no free-form advice)."""

    misconception_id: str
    intervention_level: str
    intervention_type: str
    target_skill: str
    explanation: str
    recommended_action: str

    def __post_init__(self) -> None:
        mid = _norm_id(self.misconception_id, "misconception_id")
        if not is_valid_misconception(mid):
            raise ValueError(f"Unknown misconception ID {self.misconception_id!r}.")
        level = self.intervention_level.strip() if isinstance(self.intervention_level, str) else ""
        if level not in _ALLOWED_LEVELS:
            raise ValueError(
                f"intervention_level must be one of {sorted(_ALLOWED_LEVELS)}, "
                f"got {self.intervention_level!r}."
            )
        selected = self.intervention_type.strip() if isinstance(self.intervention_type, str) else ""
        if selected not in _ALLOWED_TYPES:
            raise ValueError(
                f"intervention_type must be one of {sorted(_ALLOWED_TYPES)}, "
                f"got {self.intervention_type!r}."
            )
        skill = _require_text(self.target_skill, "target_skill", limit=200)
        explanation = _require_text(self.explanation, "explanation", limit=500)
        if len(explanation) < 10:
            raise ValueError("explanation must be at least 10 characters.")
        action = _require_text(self.recommended_action, "recommended_action", limit=500)
        if len(action) < 10:
            raise ValueError("recommended_action must be at least 10 characters.")
        object.__setattr__(self, "misconception_id", mid)
        object.__setattr__(self, "intervention_level", level)
        object.__setattr__(self, "intervention_type", selected)
        object.__setattr__(self, "target_skill", skill)
        object.__setattr__(self, "explanation", explanation)
        object.__setattr__(self, "recommended_action", action)

    def to_dict(self) -> dict[str, Any]:
        return {
            "misconception_id": self.misconception_id,
            "intervention_level": self.intervention_level,
            "intervention_type": self.intervention_type,
            "target_skill": self.target_skill,
            "explanation": self.explanation,
            "recommended_action": self.recommended_action,
        }


def _as_diagnosis(value: Diagnosis | dict[str, Any]) -> Diagnosis:
    if isinstance(value, Diagnosis):
        return value
    if isinstance(value, dict):
        try:
            return Diagnosis(
                concept_id=value["concept_id"],
                misconception_id=value["misconception_id"],
                confidence=value["confidence"],
                explanation=value["explanation"],
                evidence_refs=value["evidence_refs"],
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid diagnosis mapping: {exc}.") from exc
    raise TypeError(
        f"diagnosis must be Diagnosis or dict, got {type(value).__name__}."
    )


def _as_pack(pack: EvidencePack | dict[str, Any]) -> EvidencePack:
    if isinstance(pack, EvidencePack):
        return pack
    if isinstance(pack, dict):
        return EvidencePack.from_dict(pack)
    raise TypeError(f"pack must be EvidencePack or dict, got {type(pack).__name__}.")


def _occurrence_count(pack: EvidencePack, mid: str) -> int:
    for entry in pack.misconception_history:
        if entry.misconception_id == mid:
            return int(entry.occurrence_count)
    return 0


def _is_recurring(pack: EvidencePack, mid: str) -> bool:
    for flag in pack.recurring_flags:
        if flag.misconception_id == mid:
            return bool(flag.is_recurring)
    return False


def level_for_history(*, occurrence_count: int, is_recurring: bool) -> str:
    """Deterministic level from existing history (never the raw failure)."""
    if bool(is_recurring) and int(occurrence_count) >= _RETEACH_MIN_OCCURRENCES:
        return "L4"
    if bool(is_recurring):
        return "L3"
    if int(occurrence_count) >= 1:
        return "L2"
    return "L1"


def _decisive_facts(pack: EvidencePack) -> tuple[str | None, str | None, str | None]:
    if not pack.failed_tests:
        return None, None, None
    first = pack.failed_tests[0]
    return first.test_id, first.expected_output, first.actual_output


def _action_for(
    selected_type: str,
    test_id: str | None,
    expected: str | None,
    actual: str | None,
) -> str:
    if test_id is not None:
        observed = f"decisive test {test_id} (expected {expected!r}, observed {actual!r})"
    else:
        observed = "the submitted code (no failing test recorded)"
    if selected_type == "BOUNDARY_CHECK":
        return (
            f"Trace the loop on {observed}: write down the last index the "
            f"loop visits, extend the range stop so the terminal element is "
            f"included, then re-run the failing tests."
        )
    if selected_type == "TRACE_LOOP":
        return (
            f"Trace the loop iteration by iteration on {observed}: list "
            f"every value the loop variable takes, note which terminal "
            f"value is missing, adjust the range stop to be inclusive, then "
            f"re-run the failing tests."
        )
    return (
        f"Re-run {observed}, compare the expected and observed output, "
        f"revise the loop that produces the difference, then retry."
    )


def build_intervention(
    diagnosis: Diagnosis | dict[str, Any],
    pack: EvidencePack | dict[str, Any],
) -> Intervention:
    """Build the structured intervention for one diagnosis (pure).

    Raises:
        ValueError: diagnosis concept mismatches the pack, the
            misconception is unknown or not a pack candidate (never map an
            ungrounded ID), or any field violates its shape contract.
    """
    resolved = _as_diagnosis(diagnosis)
    evidence = _as_pack(pack)
    mid = resolved.misconception_id.strip().upper()
    if resolved.concept_id.strip().upper() != evidence.concept_id:
        raise ValueError(
            f"diagnosis concept {resolved.concept_id!r} does not match pack "
            f"concept {evidence.concept_id!r}."
        )
    if not is_valid_misconception(mid):
        raise ValueError(f"Unknown misconception ID {mid!r}.")
    candidate_ids = {c.misconception_id for c in evidence.misconception_candidates}
    if mid not in candidate_ids:
        raise ValueError(
            f"misconception {mid!r} is not a pack candidate "
            f"{sorted(candidate_ids)!r}; refusing to map ungrounded IDs."
        )
    occurrences = _occurrence_count(evidence, mid)
    recurring = _is_recurring(evidence, mid)
    level = level_for_history(occurrence_count=occurrences, is_recurring=recurring)
    level_name = LEVEL_NAMES[level]
    curated = _CURATED.get(mid)
    if curated is not None:
        selected_type, skill = curated
    else:
        selected_type, skill = "TARGETED_HINT", get_misconception(mid).name
    test_id, expected, actual = _decisive_facts(evidence)
    name = get_misconception(mid).name
    if test_id is not None:
        evidence_bit = (
            f"decisive test {test_id} expected {expected!r} but observed "
            f"{actual!r}"
        )
    else:
        evidence_bit = "no failing test was recorded for this submission"
    history_bit = (
        f"recurring across {occurrences} occurrence(s)"
        if recurring
        else (
            f"seen in {occurrences} prior occurrence(s)"
            if occurrences >= 1
            else "first observed occurrence"
        )
    )
    explanation = _truncate(
        f"{level} {level_name} for {mid} ({name}): {evidence_bit}; "
        f"{history_bit}. Focus the fix on {skill}."
    )
    action = _truncate(_action_for(selected_type, test_id, expected, actual))
    return Intervention(
        misconception_id=mid,
        intervention_level=level,
        intervention_type=selected_type,
        target_skill=skill,
        explanation=explanation,
        recommended_action=action,
    )


__all__ = [
    "LEVEL_NAMES",
    "LEVEL_ORDER",
    "Intervention",
    "InterventionLevel",
    "InterventionType",
    "build_intervention",
    "level_for_history",
]
