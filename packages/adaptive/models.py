"""COGNIFY adaptive — typed models (Step 9).

Pure, deterministic, stdlib-only. No DB, no LLM, no mastery calculation,
no execution, no network, no filesystem, no environment reads.

Step 8 remains the sole owner of mastery calculation; this package only
READS mastery/band/trend values supplied by callers (e.g. thinly adapted
from ``learner_engine.get_concept_view`` / ``get_misconception_view`` dicts
via the ``from_*_view`` helpers, which tolerate extra keys and never touch
a database session).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    """Closed set of adaptive next-actions."""

    REVIEW_CONCEPT = "REVIEW_CONCEPT"
    REMEDIAL_PROBLEM = "REMEDIAL_PROBLEM"
    PRACTICE_PROBLEM = "PRACTICE_PROBLEM"
    CHALLENGE_PROBLEM = "CHALLENGE_PROBLEM"
    TRANSFER_PROBLEM = "TRANSFER_PROBLEM"
    REVIEW_PREREQUISITE = "REVIEW_PREREQUISITE"


class ReasonCode(str, Enum):
    """Machine-readable reason for a recommendation."""

    PREREQUISITE_NOT_MASTERED = "PREREQUISITE_NOT_MASTERED"
    LOW_MASTERY = "LOW_MASTERY"
    RECURRING_MISCONCEPTION = "RECURRING_MISCONCEPTION"
    EMERGING_PRACTICE = "EMERGING_PRACTICE"
    PROFICIENT_PRACTICE = "PROFICIENT_PRACTICE"
    READY_FOR_TRANSFER = "READY_FOR_TRANSFER"
    READY_FOR_CHALLENGE = "READY_FOR_CHALLENGE"
    DECLINING_TREND = "DECLINING_TREND"
    HIGH_HINT_DEPENDENCE = "HIGH_HINT_DEPENDENCE"


VALID_TRENDS: tuple[str, ...] = ("unknown", "stable", "improving", "declining")
VALID_BANDS: tuple[str, ...] = ("novice", "emerging", "proficient", "mastered", "unknown")
VALID_VARIANT_ROLES: tuple[str, ...] = ("canonical", "transfer", "remedial")


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


def _require_concept_id(value: object) -> str:
    from packages.taxonomy import is_valid_concept

    if not isinstance(value, str):
        raise TypeError(f"concept_id must be str, got {type(value).__name__}.")
    norm = value.strip().upper()
    if not norm or not is_valid_concept(norm):
        raise ValueError(f"Unknown concept_id {value!r}.")
    return norm


def _require_misconception_id(value: object) -> str:
    from packages.taxonomy import is_valid_misconception

    if not isinstance(value, str):
        raise TypeError(
            f"misconception_id must be str, got {type(value).__name__}."
        )
    norm = value.strip().upper()
    if not norm or not is_valid_misconception(norm):
        raise ValueError(f"Unknown misconception_id {value!r}.")
    return norm


def _require_unit_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number, got {type(value).__name__}.")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be in [0, 1], got {value!r}.")
    return number


def _require_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}.")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value!r}.")
    return value


def _require_language_track(value: object) -> str:
    from packages.taxonomy import SUPPORTED_LANGUAGES

    if not isinstance(value, str):
        raise TypeError(
            f"language_track must be str, got {type(value).__name__}."
        )
    norm = value.strip().lower()
    if norm not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unknown language_track {value!r}. "
            f"Use one of {list(SUPPORTED_LANGUAGES)}."
        )
    return norm


@dataclass(frozen=True)
class ConceptState:
    """Learner state for one concept (read-only input to the policy)."""

    concept_id: str
    mastery: float
    mastery_band: str
    trend: str
    attempt_count: int
    hint_dependence: float
    transfer_success_rate: float
    language_track: str | None = None

    def __post_init__(self) -> None:
        norm_concept = _require_concept_id(self.concept_id)
        mastery = _require_unit_float(self.mastery, "mastery")
        if not isinstance(self.mastery_band, str):
            raise TypeError(
                f"mastery_band must be str, got {type(self.mastery_band).__name__}."
            )
        band = self.mastery_band.strip().lower()
        if band not in VALID_BANDS:
            raise ValueError(
                f"Unknown mastery_band {self.mastery_band!r}. "
                f"Use one of {list(VALID_BANDS)}."
            )
        if not isinstance(self.trend, str):
            raise TypeError(f"trend must be str, got {type(self.trend).__name__}.")
        trend = self.trend.strip().lower()
        if trend not in VALID_TRENDS:
            raise ValueError(
                f"Unknown trend {self.trend!r}. Use one of {list(VALID_TRENDS)}."
            )
        _require_non_negative_int(self.attempt_count, "attempt_count")
        _require_unit_float(self.hint_dependence, "hint_dependence")
        _require_unit_float(self.transfer_success_rate, "transfer_success_rate")
        track: str | None = None
        if self.language_track is not None:
            track = _require_language_track(self.language_track)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "mastery", mastery)
        object.__setattr__(self, "mastery_band", band)
        object.__setattr__(self, "trend", trend)
        object.__setattr__(self, "language_track", track)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "mastery": self.mastery,
            "mastery_band": self.mastery_band,
            "trend": self.trend,
            "attempt_count": self.attempt_count,
            "hint_dependence": self.hint_dependence,
            "transfer_success_rate": self.transfer_success_rate,
            "language_track": self.language_track,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConceptState":
        if not isinstance(data, dict):
            raise TypeError(f"ConceptState.from_dict needs a dict, got {type(data).__name__}.")
        return cls(
            concept_id=data["concept_id"],
            mastery=data["mastery"],
            mastery_band=data["mastery_band"],
            trend=data["trend"],
            attempt_count=data["attempt_count"],
            hint_dependence=data["hint_dependence"],
            transfer_success_rate=data["transfer_success_rate"],
            language_track=data.get("language_track"),
        )

    @classmethod
    def from_learner_view(cls, view: dict[str, Any]) -> "ConceptState":
        """Adapt a Step 8 ``get_concept_view`` dict (tolerates extra keys).

        Never touches a DB session; pure mapping of plain data.
        """
        if not isinstance(view, dict):
            raise TypeError(f"view must be a dict, got {type(view).__name__}.")
        band = view.get("band", view.get("mastery_band", "unknown"))
        return cls(
            concept_id=view["concept_id"],
            mastery=view["mastery"],
            mastery_band=band,
            trend=view["trend"],
            attempt_count=view["attempt_count"],
            hint_dependence=view["hint_dependence"],
            transfer_success_rate=view["transfer_success_rate"],
            language_track=view.get("language_track"),
        )


@dataclass(frozen=True)
class MisconceptionState:
    """Active misconception snapshot (read-only input to the policy)."""

    misconception_id: str
    concept_id: str
    occurrence_count: int
    recent_count: int
    is_recurring: bool
    last_seen: str | None = None

    def __post_init__(self) -> None:
        from packages.taxonomy import misconception_belongs_to

        norm_m = _require_misconception_id(self.misconception_id)
        norm_concept = _require_concept_id(self.concept_id)
        if not misconception_belongs_to(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept "
                f"{norm_concept!r}."
            )
        _require_non_negative_int(self.occurrence_count, "occurrence_count")
        _require_non_negative_int(self.recent_count, "recent_count")
        if not isinstance(self.is_recurring, bool):
            raise TypeError(
                f"is_recurring must be bool, got {type(self.is_recurring).__name__}."
            )
        last = self.last_seen
        if last is not None:
            if not isinstance(last, str):
                raise TypeError(
                    f"last_seen must be str or None, got {type(last).__name__}."
                )
            if not last.strip():
                raise ValueError("last_seen must be a non-empty string or None.")
            last = last.strip()
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "last_seen", last)

    def to_dict(self) -> dict[str, Any]:
        return {
            "misconception_id": self.misconception_id,
            "concept_id": self.concept_id,
            "occurrence_count": self.occurrence_count,
            "recent_count": self.recent_count,
            "is_recurring": self.is_recurring,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MisconceptionState":
        if not isinstance(data, dict):
            raise TypeError(
                f"MisconceptionState.from_dict needs a dict, got {type(data).__name__}."
            )
        return cls(
            misconception_id=data["misconception_id"],
            concept_id=data["concept_id"],
            occurrence_count=data.get("occurrence_count", 0),
            recent_count=data.get("recent_count", 0),
            is_recurring=bool(data.get("is_recurring", False)),
            last_seen=data.get("last_seen"),
        )

    @classmethod
    def from_misconception_view(cls, view: dict[str, Any]) -> "MisconceptionState":
        """Adapt a Step 8 ``get_misconception_view`` dict (pure mapping)."""
        if not isinstance(view, dict):
            raise TypeError(f"view must be a dict, got {type(view).__name__}.")
        return cls(
            misconception_id=view["misconception_id"],
            concept_id=view["concept_id"],
            occurrence_count=view.get("occurrence_count", 0),
            recent_count=view.get("recent_count", view.get("recent_occurrence_count", 0)),
            is_recurring=bool(view.get("is_recurring", False)),
            last_seen=view.get("last_seen_at", view.get("last_seen")),
        )


@dataclass(frozen=True)
class CurriculumInfo:
    """Curriculum metadata for one concept."""

    concept_id: str
    prerequisites: tuple[str, ...] | list[str] = ()
    mastery_threshold: float = 0.60

    def __post_init__(self) -> None:
        norm_concept = _require_concept_id(self.concept_id)
        if not isinstance(self.prerequisites, (list, tuple)):
            raise TypeError(
                "prerequisites must be a list/tuple of concept IDs, "
                f"got {type(self.prerequisites).__name__}."
            )
        prereqs: list[str] = []
        for raw in self.prerequisites:
            norm = _require_concept_id(raw)
            if norm == norm_concept:
                raise ValueError(f"Concept {norm_concept!r} cannot require itself.")
            prereqs.append(norm)
        if len(set(prereqs)) != len(prereqs):
            raise ValueError(f"prerequisites contains duplicates: {prereqs!r}.")
        threshold = _require_unit_float(self.mastery_threshold, "mastery_threshold")
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "prerequisites", tuple(prereqs))
        object.__setattr__(self, "mastery_threshold", threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "prerequisites": list(self.prerequisites),
            "mastery_threshold": self.mastery_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CurriculumInfo":
        if not isinstance(data, dict):
            raise TypeError(
                f"CurriculumInfo.from_dict needs a dict, got {type(data).__name__}."
            )
        return cls(
            concept_id=data["concept_id"],
            prerequisites=data.get("prerequisites", ()),
            mastery_threshold=data.get("mastery_threshold", 0.60),
        )

    @classmethod
    def from_taxonomy(cls, concept_id: str, mastery_threshold: float = 0.60) -> "CurriculumInfo":
        """Build from the taxonomy's canonical prerequisites (pure)."""
        from packages.taxonomy import get_concept

        concept = get_concept(concept_id)
        return cls(
            concept_id=concept.id,
            prerequisites=tuple(concept.prerequisites),
            mastery_threshold=mastery_threshold,
        )


@dataclass(frozen=True)
class ProblemInfo:
    """Problem catalog metadata (no code, no execution)."""

    problem_id: str
    concept_id: str
    difficulty: int
    isomorphic_group_id: str
    variant_role: str = "canonical"

    def __post_init__(self) -> None:
        pid = _require_non_empty_str(self.problem_id, "problem_id")
        norm_concept = _require_concept_id(self.concept_id)
        if type(self.difficulty) is not int or not 1 <= self.difficulty <= 5:
            raise ValueError(f"difficulty must be an int in [1, 5], got {self.difficulty!r}.")
        gid = _require_non_empty_str(self.isomorphic_group_id, "isomorphic_group_id")
        if not isinstance(self.variant_role, str):
            raise TypeError(
                f"variant_role must be str, got {type(self.variant_role).__name__}."
            )
        role = self.variant_role.strip().lower()
        if role not in VALID_VARIANT_ROLES:
            raise ValueError(
                f"Unknown variant_role {self.variant_role!r}. "
                f"Use one of {list(VALID_VARIANT_ROLES)}."
            )
        object.__setattr__(self, "problem_id", pid)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "isomorphic_group_id", gid)
        object.__setattr__(self, "variant_role", role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "concept_id": self.concept_id,
            "difficulty": self.difficulty,
            "isomorphic_group_id": self.isomorphic_group_id,
            "variant_role": self.variant_role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemInfo":
        if not isinstance(data, dict):
            raise TypeError(
                f"ProblemInfo.from_dict needs a dict, got {type(data).__name__}."
            )
        return cls(
            problem_id=data["problem_id"],
            concept_id=data["concept_id"],
            difficulty=data["difficulty"],
            isomorphic_group_id=data["isomorphic_group_id"],
            variant_role=data.get("variant_role", "canonical"),
        )


@dataclass(frozen=True)
class Recommendation:
    """One ranked next-action (output of the policy)."""

    action_type: ActionType
    concept_id: str
    priority: int
    reason_code: ReasonCode
    reason: str
    supporting_evidence: dict[str, Any]
    problem_id: str | None = None
    misconception_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action_type, ActionType):
            raise TypeError(
                f"action_type must be ActionType, got {type(self.action_type).__name__}."
            )
        norm_concept = _require_concept_id(self.concept_id)
        if type(self.priority) is not int:
            raise TypeError(f"priority must be int, got {type(self.priority).__name__}.")
        if not isinstance(self.reason_code, ReasonCode):
            raise TypeError(
                f"reason_code must be ReasonCode, got {type(self.reason_code).__name__}."
            )
        if not isinstance(self.reason, str):
            raise TypeError(f"reason must be str, got {type(self.reason).__name__}.")
        text = self.reason.strip()
        if not 10 <= len(text) <= 500:
            raise ValueError(
                f"reason must be 10..500 chars (concise explanation), got {len(text)}."
            )
        if not isinstance(self.supporting_evidence, dict):
            raise TypeError(
                "supporting_evidence must be a dict, "
                f"got {type(self.supporting_evidence).__name__}."
            )
        for key in self.supporting_evidence:
            if not isinstance(key, str):
                raise TypeError(
                    "supporting_evidence keys must be str, "
                    f"got {type(key).__name__}."
                )
        pid: str | None = None
        if self.problem_id is not None:
            pid = _require_non_empty_str(self.problem_id, "problem_id")
        mid: str | None = None
        if self.misconception_id is not None:
            mid = _require_misconception_id(self.misconception_id)
            from packages.taxonomy import misconception_belongs_to

            if not misconception_belongs_to(mid, norm_concept):
                raise ValueError(
                    f"Misconception {mid!r} does not belong to concept "
                    f"{norm_concept!r}."
                )
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "reason", text)
        object.__setattr__(self, "supporting_evidence", dict(self.supporting_evidence))
        object.__setattr__(self, "problem_id", pid)
        object.__setattr__(self, "misconception_id", mid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "concept_id": self.concept_id,
            "priority": self.priority,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "supporting_evidence": dict(self.supporting_evidence),
            "problem_id": self.problem_id,
            "misconception_id": self.misconception_id,
        }


__all__ = [
    "VALID_BANDS",
    "VALID_TRENDS",
    "VALID_VARIANT_ROLES",
    "ActionType",
    "ConceptState",
    "CurriculumInfo",
    "MisconceptionState",
    "ProblemInfo",
    "ReasonCode",
    "Recommendation",
]
