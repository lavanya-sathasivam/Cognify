"""COGNIFY evidence — EvidencePack data models (Step 6).

Deterministic, framework-independent (stdlib only).

An EvidencePack converts one ExecutionResult + one Problem + the *relevant*
slice of learner history into structured, read-only evidence for the future
AI diagnosis service. It is OBSERVED evidence only:

- Raw execution output is preserved verbatim (never normalized here).
- Misconceptions appear as CANDIDATES (from the problem definition), never
  as confirmed. ``confirmed_misconception_id`` is always None; the future
  diagnosis service owns confirmation.
- Only history relevant to (problem.concept_id, candidate IDs) is included.
  The full learner database is never embedded.
- No credentials, connection strings, tokens, or secrets are carried. Output
  metadata is validated to reject secret-like keys.

NOT implemented here: LLM calls, diagnosis, hint generation, mastery
calculations, adaptive policy, frontend, database access. This package never
touches the network, the filesystem, the environment, or a DB session; the
builder accepts detached plain-data snapshots only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from packages.taxonomy import (
    SUPPORTED_LANGUAGES,
    is_valid_concept,
    is_valid_misconception,
    misconception_belongs_to,
)

EVIDENCE_SCHEMA_VERSION: str = "1.0"

MAX_CODE_CHARS: int = 100_000
MAX_RECENT_EVENTS: int = 10

VALID_EXECUTION_STATUSES: tuple[str, ...] = (
    "PASSED",
    "FAILED",
    "COMPILE_ERROR",
    "RUNTIME_ERROR",
    "TIMEOUT",
)

# Constant markers that separate observed evidence from inference.
EVIDENCE_KIND: str = "observed"
INFERENCE_STATUS: str = "pending-diagnosis"

# Case-insensitive fragments; any metadata key containing one is a secret and
# is rejected in *output* evidence (builder strips them from inputs).
SECRET_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "database_url",
    "credentials",
    "private_key",
    "auth_token",
    "session_key",
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------
def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


def _require_id(value: object, field_name: str) -> str:
    text = _require_non_empty_str(value, field_name)
    if not _ID_RE.match(text):
        raise ValueError(
            f"{field_name} {value!r} is invalid. "
            "Use letters/digits plus '._-', starting with a letter/digit."
        )
    return text


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str, got {type(value).__name__}.")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}.")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value!r}.")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}.")
    if value < 1:
        raise ValueError(f"{field_name} must be >= 1, got {value!r}.")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool, got {type(value).__name__}.")
    return value


def normalize_language(language: str) -> str:
    if not isinstance(language, str):
        raise TypeError(f"language must be str, got {type(language).__name__}.")
    norm = language.strip().lower()
    if norm not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unknown language {language!r}. Use one of {list(SUPPORTED_LANGUAGES)}."
        )
    return norm


def normalize_concept_id(concept_id: str) -> str:
    if not isinstance(concept_id, str):
        raise TypeError(f"concept_id must be str, got {type(concept_id).__name__}.")
    norm = concept_id.strip().upper()
    if not norm or not is_valid_concept(norm):
        raise ValueError(f"Unknown concept ID {concept_id!r}.")
    return norm


def normalize_misconception_id(misconception_id: str) -> str:
    if not isinstance(misconception_id, str):
        raise TypeError(
            f"misconception_id must be str, got {type(misconception_id).__name__}."
        )
    norm = misconception_id.strip().upper()
    if not norm or not is_valid_misconception(norm):
        raise ValueError(f"Unknown misconception ID {misconception_id!r}.")
    return norm


def is_valid_execution_status(value: object) -> bool:
    """True iff `value` names a known execution status (case/space tolerant)."""
    return isinstance(value, str) and value.strip().upper() in VALID_EXECUTION_STATUSES


def normalize_execution_status(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"execution_status must be str, got {type(value).__name__}."
        )
    norm = value.strip().upper()
    if norm not in VALID_EXECUTION_STATUSES:
        raise ValueError(
            f"Unknown execution_status {value!r}. "
            f"Use one of {list(VALID_EXECUTION_STATUSES)}."
        )
    return norm


def _is_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower().replace("-", "_").replace(" ", "_")
    return any(frag in lowered for frag in SECRET_KEY_FRAGMENTS)


def _require_clean_metadata(value: object, field_name: str) -> dict[str, Any]:
    """Validate output metadata: must be a dict with str keys, no secrets."""
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict, got {type(value).__name__}.")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be str, got {type(key).__name__}.")
        if _is_secret_key(key):
            raise ValueError(
                f"{field_name} carries a forbidden secret-like key {key!r}; "
                "evidence must never expose credentials or secrets."
            )
    return dict(value)


def _require_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None, got {type(value).__name__}.")
    return value


def _require_optional_non_empty_id(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string or None.")
    return text


# ---------------------------------------------------------------------------
# Output evidence sub-models (what the AI service receives)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FailedTestEvidence:
    """One non-passing test, raw output preserved verbatim (no normalization)."""

    test_id: str
    input: str
    expected_output: str
    actual_output: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    time_ms: int

    def __post_init__(self) -> None:
        norm_id = _require_id(self.test_id, "test_id")
        for field_name in ("input", "expected_output", "actual_output", "stdout", "stderr"):
            _require_str(getattr(self, field_name), field_name)
        if type(self.exit_code) is not int:
            raise TypeError(
                f"exit_code must be int, got {type(self.exit_code).__name__}."
            )
        _require_bool(self.timed_out, "timed_out")
        _require_non_negative_int(self.time_ms, "time_ms")
        object.__setattr__(self, "test_id", norm_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "input": self.input,
            "expected_output": self.expected_output,
            "actual_output": self.actual_output,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "time_ms": self.time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailedTestEvidence":
        if not isinstance(data, dict):
            raise TypeError(
                f"FailedTestEvidence.from_dict needs a dict, got {type(data).__name__}."
            )
        required = (
            "test_id", "input", "expected_output", "actual_output",
            "stdout", "stderr", "exit_code", "timed_out", "time_ms",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"FailedTestEvidence dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(f"FailedTestEvidence dict has unexpected keys: {extra}.")
        return cls(
            test_id=data["test_id"],
            input=data["input"],
            expected_output=data["expected_output"],
            actual_output=data["actual_output"],
            stdout=data["stdout"],
            stderr=data["stderr"],
            exit_code=data["exit_code"],
            timed_out=data["timed_out"],
            time_ms=data["time_ms"],
        )


@dataclass(frozen=True)
class MisconceptionCandidate:
    """A misconception linked to the problem — a CANDIDATE, never confirmed.

    ``name`` / ``typical_signal`` are deterministic taxonomy snapshots copied
    at build time so the future diagnosis service need not re-resolve IDs.
    """

    misconception_id: str
    concept_id: str
    name: str
    typical_signal: str

    def __post_init__(self) -> None:
        norm_concept = normalize_concept_id(self.concept_id)
        norm_m = normalize_misconception_id(self.misconception_id)
        if not misconception_belongs_to(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept {norm_concept!r}."
            )
        _require_non_empty_str(self.name, "name")
        _require_non_empty_str(self.typical_signal, "typical_signal")
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "concept_id", norm_concept)

    def to_dict(self) -> dict[str, Any]:
        return {
            "misconception_id": self.misconception_id,
            "concept_id": self.concept_id,
            "name": self.name,
            "typical_signal": self.typical_signal,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MisconceptionCandidate":
        if not isinstance(data, dict):
            raise TypeError(
                "MisconceptionCandidate.from_dict needs a dict, "
                f"got {type(data).__name__}."
            )
        required = ("misconception_id", "concept_id", "name", "typical_signal")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"MisconceptionCandidate dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(f"MisconceptionCandidate dict has unexpected keys: {extra}.")
        return cls(
            misconception_id=data["misconception_id"],
            concept_id=data["concept_id"],
            name=data["name"],
            typical_signal=data["typical_signal"],
        )


@dataclass(frozen=True)
class ConceptHistorySummary:
    """Stored per-concept learner state, copied verbatim (never computed here).

    ``stored_mastery`` is a snapshot of the value kept by core-backend; this
    package performs no mastery calculation.
    """

    concept_id: str
    stored_mastery: float
    attempt_count: int
    successful_attempts: int
    current_band: str
    trend: str
    hint_count: int
    transfer_attempts: int
    transfer_successes: int

    def __post_init__(self) -> None:
        norm_concept = normalize_concept_id(self.concept_id)
        value = self.stored_mastery
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(
                f"stored_mastery must be a number, got {type(value).__name__}."
            )
        if not 0 <= float(value) <= 1:
            raise ValueError(f"stored_mastery must be in [0, 1], got {value!r}.")
        _require_non_negative_int(self.attempt_count, "attempt_count")
        _require_non_negative_int(self.successful_attempts, "successful_attempts")
        _require_non_empty_str(self.current_band, "current_band")
        _require_non_empty_str(self.trend, "trend")
        _require_non_negative_int(self.hint_count, "hint_count")
        _require_non_negative_int(self.transfer_attempts, "transfer_attempts")
        _require_non_negative_int(self.transfer_successes, "transfer_successes")
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "stored_mastery", float(value))
        object.__setattr__(self, "current_band", self.current_band.strip())
        object.__setattr__(self, "trend", self.trend.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "stored_mastery": self.stored_mastery,
            "attempt_count": self.attempt_count,
            "successful_attempts": self.successful_attempts,
            "current_band": self.current_band,
            "trend": self.trend,
            "hint_count": self.hint_count,
            "transfer_attempts": self.transfer_attempts,
            "transfer_successes": self.transfer_successes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConceptHistorySummary":
        if not isinstance(data, dict):
            raise TypeError(
                "ConceptHistorySummary.from_dict needs a dict, "
                f"got {type(data).__name__}."
            )
        required = (
            "concept_id", "stored_mastery", "attempt_count", "successful_attempts",
            "current_band", "trend", "hint_count", "transfer_attempts",
            "transfer_successes",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"ConceptHistorySummary dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(
                f"ConceptHistorySummary dict has unexpected keys: {extra}."
            )
        return cls(
            concept_id=data["concept_id"],
            stored_mastery=data["stored_mastery"],
            attempt_count=data["attempt_count"],
            successful_attempts=data["successful_attempts"],
            current_band=data["current_band"],
            trend=data["trend"],
            hint_count=data["hint_count"],
            transfer_attempts=data["transfer_attempts"],
            transfer_successes=data["transfer_successes"],
        )


@dataclass(frozen=True)
class MisconceptionOccurrence:
    """Previous occurrence count for one *candidate* misconception (observed)."""

    misconception_id: str
    concept_id: str
    occurrence_count: int
    active: bool
    last_seen_at: str | None = None

    def __post_init__(self) -> None:
        norm_concept = normalize_concept_id(self.concept_id)
        norm_m = normalize_misconception_id(self.misconception_id)
        if not misconception_belongs_to(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept {norm_concept!r}."
            )
        _require_non_negative_int(self.occurrence_count, "occurrence_count")
        _require_bool(self.active, "active")
        last = _require_optional_str(self.last_seen_at, "last_seen_at")
        if isinstance(last, str) and not last.strip():
            raise ValueError("last_seen_at must be a non-empty string or None.")
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "concept_id", norm_concept)

    def to_dict(self) -> dict[str, Any]:
        return {
            "misconception_id": self.misconception_id,
            "concept_id": self.concept_id,
            "occurrence_count": self.occurrence_count,
            "active": self.active,
            "last_seen_at": self.last_seen_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MisconceptionOccurrence":
        if not isinstance(data, dict):
            raise TypeError(
                "MisconceptionOccurrence.from_dict needs a dict, "
                f"got {type(data).__name__}."
            )
        required = (
            "misconception_id", "concept_id", "occurrence_count",
            "active", "last_seen_at",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"MisconceptionOccurrence dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(
                f"MisconceptionOccurrence dict has unexpected keys: {extra}."
            )
        return cls(
            misconception_id=data["misconception_id"],
            concept_id=data["concept_id"],
            occurrence_count=data["occurrence_count"],
            active=data["active"],
            last_seen_at=data["last_seen_at"],
        )


@dataclass(frozen=True)
class RecurringFlagEvidence:
    """Whether a *candidate* misconception is currently flagged recurring."""

    misconception_id: str
    concept_id: str
    is_recurring: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        norm_concept = normalize_concept_id(self.concept_id)
        norm_m = normalize_misconception_id(self.misconception_id)
        if not misconception_belongs_to(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept {norm_concept!r}."
            )
        _require_bool(self.is_recurring, "is_recurring")
        reason = _require_optional_str(self.reason, "reason")
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "reason", reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "misconception_id": self.misconception_id,
            "concept_id": self.concept_id,
            "is_recurring": self.is_recurring,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecurringFlagEvidence":
        if not isinstance(data, dict):
            raise TypeError(
                "RecurringFlagEvidence.from_dict needs a dict, "
                f"got {type(data).__name__}."
            )
        required = ("misconception_id", "concept_id", "is_recurring", "reason")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"RecurringFlagEvidence dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(
                f"RecurringFlagEvidence dict has unexpected keys: {extra}."
            )
        return cls(
            misconception_id=data["misconception_id"],
            concept_id=data["concept_id"],
            is_recurring=data["is_recurring"],
            reason=data["reason"],
        )


@dataclass(frozen=True)
class RelevantEventEvidence:
    """One recent learner event for the pack's concept (observed, capped).

    ``metadata`` is a sanitized copy: secret-like keys are rejected here so no
    EvidencePack can ever carry credentials.
    """

    event_type: str
    concept_id: str
    misconception_id: str | None
    created_at: str | None
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        norm_type = _require_non_empty_str(self.event_type, "event_type")
        norm_concept = normalize_concept_id(self.concept_id)
        norm_m: str | None = None
        if self.misconception_id is not None:
            norm_m = normalize_misconception_id(self.misconception_id)
            if not misconception_belongs_to(norm_m, norm_concept):
                raise ValueError(
                    f"Misconception {norm_m!r} does not belong to concept "
                    f"{norm_concept!r}."
                )
        created = _require_optional_str(self.created_at, "created_at")
        if isinstance(created, str) and not created.strip():
            raise ValueError("created_at must be a non-empty string or None.")
        clean = _require_clean_metadata(self.metadata, "metadata")
        object.__setattr__(self, "event_type", norm_type)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "metadata", clean)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "concept_id": self.concept_id,
            "misconception_id": self.misconception_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelevantEventEvidence":
        if not isinstance(data, dict):
            raise TypeError(
                "RelevantEventEvidence.from_dict needs a dict, "
                f"got {type(data).__name__}."
            )
        required = (
            "event_type", "concept_id", "misconception_id",
            "created_at", "metadata",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"RelevantEventEvidence dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(
                f"RelevantEventEvidence dict has unexpected keys: {extra}."
            )
        return cls(
            event_type=data["event_type"],
            concept_id=data["concept_id"],
            misconception_id=data["misconception_id"],
            created_at=data["created_at"],
            metadata=data["metadata"],
        )


@dataclass(frozen=True)
class LearnerRef:
    """Minimal learner scoping: opaque IDs plus language track (no secrets)."""

    user_id: int
    journey_id: int
    language_track: str

    def __post_init__(self) -> None:
        _require_positive_int(self.user_id, "user_id")
        _require_positive_int(self.journey_id, "journey_id")
        norm_track = normalize_language(self.language_track)
        object.__setattr__(self, "language_track", norm_track)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "journey_id": self.journey_id,
            "language_track": self.language_track,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnerRef":
        if not isinstance(data, dict):
            raise TypeError(
                f"LearnerRef.from_dict needs a dict, got {type(data).__name__}."
            )
        required = ("user_id", "journey_id", "language_track")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"LearnerRef dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(f"LearnerRef dict has unexpected keys: {extra}.")
        return cls(
            user_id=data["user_id"],
            journey_id=data["journey_id"],
            language_track=data["language_track"],
        )


# ---------------------------------------------------------------------------
# Input snapshot DTOs (detached plain data; what core-backend passes in)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConceptStateSnapshot:
    """Detached copy of one LearnerConceptState row (input to the builder)."""

    concept_id: str
    stored_mastery: float = 0.0
    attempt_count: int = 0
    successful_attempts: int = 0
    current_band: str = "unassessed"
    trend: str = "unknown"
    hint_count: int = 0
    transfer_attempts: int = 0
    transfer_successes: int = 0

    def __post_init__(self) -> None:
        summary = ConceptHistorySummary(
            concept_id=self.concept_id,
            stored_mastery=self.stored_mastery,
            attempt_count=self.attempt_count,
            successful_attempts=self.successful_attempts,
            current_band=self.current_band,
            trend=self.trend,
            hint_count=self.hint_count,
            transfer_attempts=self.transfer_attempts,
            transfer_successes=self.transfer_successes,
        )
        object.__setattr__(self, "concept_id", summary.concept_id)
        object.__setattr__(self, "stored_mastery", summary.stored_mastery)
        object.__setattr__(self, "current_band", summary.current_band)
        object.__setattr__(self, "trend", summary.trend)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "stored_mastery": self.stored_mastery,
            "attempt_count": self.attempt_count,
            "successful_attempts": self.successful_attempts,
            "current_band": self.current_band,
            "trend": self.trend,
            "hint_count": self.hint_count,
            "transfer_attempts": self.transfer_attempts,
            "transfer_successes": self.transfer_successes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConceptStateSnapshot":
        if not isinstance(data, dict):
            raise TypeError(
                "ConceptStateSnapshot.from_dict needs a dict, "
                f"got {type(data).__name__}."
            )
        return cls(**{k: data[k] for k in (
            "concept_id", "stored_mastery", "attempt_count", "successful_attempts",
            "current_band", "trend", "hint_count", "transfer_attempts",
            "transfer_successes",
        ) if k in data})


@dataclass(frozen=True)
class CounterSnapshot:
    """Detached copy of one MisconceptionCounter row (input to the builder)."""

    concept_id: str
    misconception_id: str
    occurrence_count: int = 0
    active: bool = True
    last_seen_at: str | None = None

    def __post_init__(self) -> None:
        norm_concept = normalize_concept_id(self.concept_id)
        norm_m = normalize_misconception_id(self.misconception_id)
        if not misconception_belongs_to(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept {norm_concept!r}."
            )
        _require_non_negative_int(self.occurrence_count, "occurrence_count")
        _require_bool(self.active, "active")
        last = _require_optional_str(self.last_seen_at, "last_seen_at")
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "last_seen_at", last)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "misconception_id": self.misconception_id,
            "occurrence_count": self.occurrence_count,
            "active": self.active,
            "last_seen_at": self.last_seen_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CounterSnapshot":
        if not isinstance(data, dict):
            raise TypeError(
                f"CounterSnapshot.from_dict needs a dict, got {type(data).__name__}."
            )
        return cls(
            concept_id=data["concept_id"],
            misconception_id=data["misconception_id"],
            occurrence_count=data.get("occurrence_count", 0),
            active=data.get("active", True),
            last_seen_at=data.get("last_seen_at"),
        )


@dataclass(frozen=True)
class FlagSnapshot:
    """Detached copy of one RecurringFlag row (input to the builder)."""

    concept_id: str
    misconception_id: str
    is_recurring: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        norm_concept = normalize_concept_id(self.concept_id)
        norm_m = normalize_misconception_id(self.misconception_id)
        if not misconception_belongs_to(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept {norm_concept!r}."
            )
        _require_bool(self.is_recurring, "is_recurring")
        reason = _require_optional_str(self.reason, "reason")
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "reason", reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "misconception_id": self.misconception_id,
            "is_recurring": self.is_recurring,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlagSnapshot":
        if not isinstance(data, dict):
            raise TypeError(
                f"FlagSnapshot.from_dict needs a dict, got {type(data).__name__}."
            )
        return cls(
            concept_id=data["concept_id"],
            misconception_id=data["misconception_id"],
            is_recurring=data.get("is_recurring", False),
            reason=data.get("reason"),
        )


@dataclass(frozen=True)
class EventSnapshot:
    """Detached copy of one LearnerEvent row (input to the builder).

    Input metadata may contain anything; the builder sanitizes secret-like
    keys before they reach output evidence.
    """

    event_type: str
    concept_id: str
    misconception_id: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        norm_type = _require_non_empty_str(self.event_type, "event_type")
        norm_concept = normalize_concept_id(self.concept_id)
        norm_m: str | None = None
        if self.misconception_id is not None:
            norm_m = normalize_misconception_id(self.misconception_id)
            if not misconception_belongs_to(norm_m, norm_concept):
                raise ValueError(
                    f"Misconception {norm_m!r} does not belong to concept "
                    f"{norm_concept!r}."
                )
        created = _require_optional_str(self.created_at, "created_at")
        md = self.metadata if self.metadata is not None else {}
        if not isinstance(md, dict):
            raise TypeError(f"metadata must be a dict, got {type(md).__name__}.")
        object.__setattr__(self, "event_type", norm_type)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "metadata", dict(md))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "concept_id": self.concept_id,
            "misconception_id": self.misconception_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventSnapshot":
        if not isinstance(data, dict):
            raise TypeError(
                f"EventSnapshot.from_dict needs a dict, got {type(data).__name__}."
            )
        return cls(
            event_type=data["event_type"],
            concept_id=data["concept_id"],
            misconception_id=data.get("misconception_id"),
            created_at=data.get("created_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class LearnerSnapshot:
    """Detached learner slice the builder may read (never a DB session).

    Callers (core-backend) convert ORM rows into these plain DTOs first, so
    database URLs, engines, and sessions never cross into this package.
    """

    user_id: int
    journey_id: int
    language_track: str
    concept_state: ConceptStateSnapshot | None = None
    counters: tuple[CounterSnapshot, ...] | list[CounterSnapshot] = ()
    flags: tuple[FlagSnapshot, ...] | list[FlagSnapshot] = ()
    events: tuple[EventSnapshot, ...] | list[EventSnapshot] = ()

    def __post_init__(self) -> None:
        _require_positive_int(self.user_id, "user_id")
        _require_positive_int(self.journey_id, "journey_id")
        norm_track = normalize_language(self.language_track)
        if self.concept_state is not None and not isinstance(
            self.concept_state, ConceptStateSnapshot
        ):
            raise TypeError(
                "concept_state must be ConceptStateSnapshot or None, "
                f"got {type(self.concept_state).__name__}."
            )
        for field_name, want in (
            ("counters", CounterSnapshot),
            ("flags", FlagSnapshot),
            ("events", EventSnapshot),
        ):
            value = getattr(self, field_name)
            if not isinstance(value, (list, tuple)):
                raise TypeError(
                    f"{field_name} must be a list/tuple of {want.__name__}, "
                    f"got {type(value).__name__}."
                )
            for item in value:
                if not isinstance(item, want):
                    raise TypeError(
                        f"{field_name} entries must be {want.__name__}, "
                        f"got {type(item).__name__}."
                    )
        object.__setattr__(self, "language_track", norm_track)
        object.__setattr__(self, "counters", tuple(self.counters))
        object.__setattr__(self, "flags", tuple(self.flags))
        object.__setattr__(self, "events", tuple(self.events))

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "journey_id": self.journey_id,
            "language_track": self.language_track,
            "concept_state": (
                self.concept_state.to_dict() if self.concept_state is not None else None
            ),
            "counters": [c.to_dict() for c in self.counters],
            "flags": [f.to_dict() for f in self.flags],
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnerSnapshot":
        if not isinstance(data, dict):
            raise TypeError(
                f"LearnerSnapshot.from_dict needs a dict, got {type(data).__name__}."
            )
        state = data.get("concept_state")
        return cls(
            user_id=data["user_id"],
            journey_id=data["journey_id"],
            language_track=data["language_track"],
            concept_state=(
                ConceptStateSnapshot.from_dict(state) if state is not None else None
            ),
            counters=tuple(
                c if isinstance(c, CounterSnapshot) else CounterSnapshot.from_dict(c)
                for c in data.get("counters", ())
            ),
            flags=tuple(
                f if isinstance(f, FlagSnapshot) else FlagSnapshot.from_dict(f)
                for f in data.get("flags", ())
            ),
            events=tuple(
                e if isinstance(e, EventSnapshot) else EventSnapshot.from_dict(e)
                for e in data.get("events", ())
            ),
        )


# ---------------------------------------------------------------------------
# EvidencePack (top-level output)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidencePack:
    """Deterministic observed evidence for one submission (read-only for AI).

    Sections:
      - submission: code / language / problem_id / concept_id (observed).
      - candidates: misconception CANDIDATES from the problem (not confirmed).
      - execution: raw status / timing / stdout / stderr / failed tests.
      - learner: minimal scoping ref + same-concept history slice only.
      - markers: evidence_kind="observed", confirmed None, status pending.

    No field here is inferred: there is no diagnosis, hint, mastery formula,
    or adaptive decision. The future diagnosis service owns all inference.
    """

    schema_version: str
    code: str
    language: str
    problem_id: str
    concept_id: str
    misconception_candidates: tuple[MisconceptionCandidate, ...] | list[MisconceptionCandidate]
    execution_status: str
    execution_time_ms: int
    stdout: str
    stderr: str
    passed_count: int
    failed_count: int
    failed_test_id: str | None
    expected_output: str | None
    actual_output: str | None
    failed_tests: tuple[FailedTestEvidence, ...] | list[FailedTestEvidence]
    learner: LearnerRef
    concept_history: ConceptHistorySummary | None
    misconception_history: tuple[MisconceptionOccurrence, ...] | list[MisconceptionOccurrence]
    recurring_flags: tuple[RecurringFlagEvidence, ...] | list[RecurringFlagEvidence]
    recent_events: tuple[RelevantEventEvidence, ...] | list[RelevantEventEvidence]
    evidence_kind: str = EVIDENCE_KIND
    confirmed_misconception_id: None = None
    inference_status: str = INFERENCE_STATUS

    def __post_init__(self) -> None:
        if self.schema_version != EVIDENCE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {EVIDENCE_SCHEMA_VERSION!r}, "
                f"got {self.schema_version!r}."
            )
        # Submission (code preserved verbatim; only validated, never altered).
        if not isinstance(self.code, str) or not self.code.strip():
            raise (
                TypeError(f"code must be str, got {type(self.code).__name__}.")
                if not isinstance(self.code, str)
                else ValueError("code must be a non-empty string.")
            )
        if len(self.code) > MAX_CODE_CHARS:
            raise ValueError(f"code exceeds {MAX_CODE_CHARS} characters.")
        norm_lang = normalize_language(self.language)
        norm_problem_id = _require_id(self.problem_id, "problem_id")
        norm_concept = normalize_concept_id(self.concept_id)

        # Candidates: >= 1, unique, all belonging to this concept.
        if not isinstance(self.misconception_candidates, (list, tuple)):
            raise TypeError("misconception_candidates must be a list/tuple.")
        candidates = tuple(self.misconception_candidates)
        if len(candidates) == 0:
            raise ValueError("misconception_candidates must contain at least one entry.")
        for item in candidates:
            if not isinstance(item, MisconceptionCandidate):
                raise TypeError(
                    "misconception_candidates entries must be "
                    f"MisconceptionCandidate, got {type(item).__name__}."
                )
            if item.concept_id != norm_concept:
                raise ValueError(
                    f"Candidate {item.misconception_id!r} belongs to concept "
                    f"{item.concept_id!r}, not pack concept {norm_concept!r}."
                )
        candidate_ids = [c.misconception_id for c in candidates]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError(
                f"misconception_candidates contains duplicates: {candidate_ids!r}."
            )
        candidate_set = set(candidate_ids)

        # Execution (raw strings preserved verbatim).
        norm_status = normalize_execution_status(self.execution_status)
        _require_non_negative_int(self.execution_time_ms, "execution_time_ms")
        _require_str(self.stdout, "stdout")
        _require_str(self.stderr, "stderr")
        _require_non_negative_int(self.passed_count, "passed_count")
        _require_non_negative_int(self.failed_count, "failed_count")
        failed_id = _require_optional_non_empty_id(self.failed_test_id, "failed_test_id")
        expected = _require_optional_str(self.expected_output, "expected_output")
        actual = _require_optional_str(self.actual_output, "actual_output")

        if not isinstance(self.failed_tests, (list, tuple)):
            raise TypeError("failed_tests must be a list/tuple.")
        failed_tests = tuple(self.failed_tests)
        for item in failed_tests:
            if not isinstance(item, FailedTestEvidence):
                raise TypeError(
                    "failed_tests entries must be FailedTestEvidence, "
                    f"got {type(item).__name__}."
                )
        failed_ids = [t.test_id for t in failed_tests]
        if len(set(failed_ids)) != len(failed_ids):
            raise ValueError(f"failed_tests contains duplicate IDs: {failed_ids!r}.")

        # Consistency between counts, decisive pointers, and failed_tests.
        if self.failed_count == 0:
            if failed_id is not None:
                raise ValueError("failed_test_id must be None when failed_count is 0.")
            if expected is not None or actual is not None:
                raise ValueError(
                    "expected_output/actual_output must be None when failed_count is 0."
                )
            if len(failed_tests) != 0:
                raise ValueError("failed_tests must be empty when failed_count is 0.")
        else:
            if failed_id is None:
                raise ValueError(
                    "failed_test_id is required when failed_count > 0."
                )
            if len(failed_tests) != self.failed_count:
                raise ValueError(
                    f"len(failed_tests)={len(failed_tests)} != "
                    f"failed_count={self.failed_count}."
                )
            decisive = failed_tests[0]
            if failed_id != decisive.test_id:
                raise ValueError(
                    f"failed_test_id {failed_id!r} must match first failed test "
                    f"{decisive.test_id!r}."
                )
            if expected != decisive.expected_output or actual != decisive.actual_output:
                raise ValueError(
                    "Top-level expected_output/actual_output must mirror the "
                    "first failed test (decisive failure)."
                )
            if self.stdout != decisive.stdout or self.stderr != decisive.stderr:
                raise ValueError(
                    "Top-level stdout/stderr must mirror the first failed test "
                    "(decisive failure) so raw evidence is preserved intact."
                )

        # Learner scoping (track separation: history must match submission).
        if not isinstance(self.learner, LearnerRef):
            raise TypeError(
                f"learner must be LearnerRef, got {type(self.learner).__name__}."
            )
        if self.learner.language_track != norm_lang:
            raise ValueError(
                f"Learner track {self.learner.language_track!r} does not match "
                f"submission language {norm_lang!r} (tracks must not cross)."
            )

        # Concept history: same concept only (None allowed for new learners).
        if self.concept_history is not None:
            if not isinstance(self.concept_history, ConceptHistorySummary):
                raise TypeError(
                    "concept_history must be ConceptHistorySummary or None, "
                    f"got {type(self.concept_history).__name__}."
                )
            if self.concept_history.concept_id != norm_concept:
                raise ValueError(
                    f"concept_history is for {self.concept_history.concept_id!r}, "
                    f"not pack concept {norm_concept!r}; include only relevant history."
                )

        # Misconception history / flags: candidate IDs only, canonical order.
        if not isinstance(self.misconception_history, (list, tuple)):
            raise TypeError("misconception_history must be a list/tuple.")
        history = tuple(self.misconception_history)
        for item in history:
            if not isinstance(item, MisconceptionOccurrence):
                raise TypeError(
                    "misconception_history entries must be MisconceptionOccurrence, "
                    f"got {type(item).__name__}."
                )
            if item.concept_id != norm_concept:
                raise ValueError(
                    f"History entry {item.misconception_id!r} is for concept "
                    f"{item.concept_id!r}, not pack concept {norm_concept!r}."
                )
            if item.misconception_id not in candidate_set:
                raise ValueError(
                    f"History entry {item.misconception_id!r} is not a candidate "
                    f"{sorted(candidate_set)!r}; include only relevant history."
                )
        history_ids = [h.misconception_id for h in history]
        if len(set(history_ids)) != len(history_ids):
            raise ValueError(
                f"misconception_history contains duplicates: {history_ids!r}."
            )
        if history_ids != sorted(history_ids):
            raise ValueError(
                "misconception_history must be sorted by misconception_id "
                "(deterministic canonical order)."
            )

        if not isinstance(self.recurring_flags, (list, tuple)):
            raise TypeError("recurring_flags must be a list/tuple.")
        flags = tuple(self.recurring_flags)
        for item in flags:
            if not isinstance(item, RecurringFlagEvidence):
                raise TypeError(
                    "recurring_flags entries must be RecurringFlagEvidence, "
                    f"got {type(item).__name__}."
                )
            if item.concept_id != norm_concept:
                raise ValueError(
                    f"Flag {item.misconception_id!r} is for concept "
                    f"{item.concept_id!r}, not pack concept {norm_concept!r}."
                )
            if item.misconception_id not in candidate_set:
                raise ValueError(
                    f"Flag {item.misconception_id!r} is not a candidate "
                    f"{sorted(candidate_set)!r}; include only relevant history."
                )
        flag_ids = [f.misconception_id for f in flags]
        if len(set(flag_ids)) != len(flag_ids):
            raise ValueError(f"recurring_flags contains duplicates: {flag_ids!r}.")
        if flag_ids != sorted(flag_ids):
            raise ValueError(
                "recurring_flags must be sorted by misconception_id "
                "(deterministic canonical order)."
            )

        # Recent events: same concept only, capped.
        if not isinstance(self.recent_events, (list, tuple)):
            raise TypeError("recent_events must be a list/tuple.")
        events = tuple(self.recent_events)
        if len(events) > MAX_RECENT_EVENTS:
            raise ValueError(
                f"recent_events holds {len(events)} entries, more than the "
                f"maximum {MAX_RECENT_EVENTS}; include only relevant history."
            )
        for item in events:
            if not isinstance(item, RelevantEventEvidence):
                raise TypeError(
                    "recent_events entries must be RelevantEventEvidence, "
                    f"got {type(item).__name__}."
                )
            if item.concept_id != norm_concept:
                raise ValueError(
                    f"Event {item.event_type!r} is for concept {item.concept_id!r}, "
                    f"not pack concept {norm_concept!r}."
                )

        # Observed-vs-inferred markers: fixed constants, never a confirmation.
        if self.evidence_kind != EVIDENCE_KIND:
            raise ValueError(
                f"evidence_kind must be {EVIDENCE_KIND!r} (observed evidence only), "
                f"got {self.evidence_kind!r}."
            )
        if self.confirmed_misconception_id is not None:
            raise ValueError(
                "confirmed_misconception_id must be None: an EvidencePack never "
                "confirms a misconception (diagnosis owns that)."
            )
        if self.inference_status != INFERENCE_STATUS:
            raise ValueError(
                f"inference_status must be {INFERENCE_STATUS!r}, "
                f"got {self.inference_status!r}."
            )

        # Store normalized / canonical values.
        object.__setattr__(self, "language", norm_lang)
        object.__setattr__(self, "problem_id", norm_problem_id)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "misconception_candidates", candidates)
        object.__setattr__(self, "execution_status", norm_status)
        object.__setattr__(self, "failed_test_id", failed_id)
        object.__setattr__(self, "expected_output", expected)
        object.__setattr__(self, "actual_output", actual)
        object.__setattr__(self, "failed_tests", failed_tests)
        object.__setattr__(self, "misconception_history", history)
        object.__setattr__(self, "recurring_flags", flags)
        object.__setattr__(self, "recent_events", events)

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping (lists, not tuples)."""
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "language": self.language,
            "problem_id": self.problem_id,
            "concept_id": self.concept_id,
            "misconception_candidates": [c.to_dict() for c in self.misconception_candidates],
            "execution_status": self.execution_status,
            "execution_time_ms": self.execution_time_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "failed_test_id": self.failed_test_id,
            "expected_output": self.expected_output,
            "actual_output": self.actual_output,
            "failed_tests": [t.to_dict() for t in self.failed_tests],
            "learner": self.learner.to_dict(),
            "concept_history": (
                self.concept_history.to_dict() if self.concept_history is not None else None
            ),
            "misconception_history": [h.to_dict() for h in self.misconception_history],
            "recurring_flags": [f.to_dict() for f in self.recurring_flags],
            "recent_events": [e.to_dict() for e in self.recent_events],
            "evidence_kind": self.evidence_kind,
            "confirmed_misconception_id": self.confirmed_misconception_id,
            "inference_status": self.inference_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidencePack":
        if not isinstance(data, dict):
            raise TypeError(
                f"EvidencePack.from_dict needs a dict, got {type(data).__name__}."
            )
        required = (
            "schema_version", "code", "language", "problem_id", "concept_id",
            "misconception_candidates", "execution_status", "execution_time_ms",
            "stdout", "stderr", "passed_count", "failed_count", "failed_test_id",
            "expected_output", "actual_output", "failed_tests", "learner",
            "concept_history", "misconception_history", "recurring_flags",
            "recent_events", "evidence_kind", "confirmed_misconception_id",
            "inference_status",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"EvidencePack dict missing keys: {missing}.")
        extra = [k for k in data if k not in required]
        if extra:
            raise ValueError(
                f"EvidencePack dict has unexpected keys: {extra}. "
                "Evidence must not be modified with extra fields."
            )
        raw_candidates = data["misconception_candidates"]
        raw_failed = data["failed_tests"]
        raw_history = data["misconception_history"]
        raw_flags = data["recurring_flags"]
        raw_events = data["recent_events"]
        if not isinstance(raw_candidates, (list, tuple)):
            raise TypeError("misconception_candidates must be a list.")
        if not isinstance(raw_failed, (list, tuple)):
            raise TypeError("failed_tests must be a list.")
        if not isinstance(raw_history, (list, tuple)):
            raise TypeError("misconception_history must be a list.")
        if not isinstance(raw_flags, (list, tuple)):
            raise TypeError("recurring_flags must be a list.")
        if not isinstance(raw_events, (list, tuple)):
            raise TypeError("recent_events must be a list.")
        raw_concept_history = data["concept_history"]
        return cls(
            schema_version=data["schema_version"],
            code=data["code"],
            language=data["language"],
            problem_id=data["problem_id"],
            concept_id=data["concept_id"],
            misconception_candidates=tuple(
                c if isinstance(c, MisconceptionCandidate)
                else MisconceptionCandidate.from_dict(c)
                for c in raw_candidates
            ),
            execution_status=data["execution_status"],
            execution_time_ms=data["execution_time_ms"],
            stdout=data["stdout"],
            stderr=data["stderr"],
            passed_count=data["passed_count"],
            failed_count=data["failed_count"],
            failed_test_id=data["failed_test_id"],
            expected_output=data["expected_output"],
            actual_output=data["actual_output"],
            failed_tests=tuple(
                t if isinstance(t, FailedTestEvidence) else FailedTestEvidence.from_dict(t)
                for t in raw_failed
            ),
            learner=(
                data["learner"] if isinstance(data["learner"], LearnerRef)
                else LearnerRef.from_dict(data["learner"])
            ),
            concept_history=(
                None if raw_concept_history is None
                else (
                    raw_concept_history
                    if isinstance(raw_concept_history, ConceptHistorySummary)
                    else ConceptHistorySummary.from_dict(raw_concept_history)
                )
            ),
            misconception_history=tuple(
                h if isinstance(h, MisconceptionOccurrence)
                else MisconceptionOccurrence.from_dict(h)
                for h in raw_history
            ),
            recurring_flags=tuple(
                f if isinstance(f, RecurringFlagEvidence)
                else RecurringFlagEvidence.from_dict(f)
                for f in raw_flags
            ),
            recent_events=tuple(
                e if isinstance(e, RelevantEventEvidence)
                else RelevantEventEvidence.from_dict(e)
                for e in raw_events
            ),
            evidence_kind=data["evidence_kind"],
            confirmed_misconception_id=data["confirmed_misconception_id"],
            inference_status=data["inference_status"],
        )


__all__ = [
    "EVIDENCE_KIND",
    "EVIDENCE_SCHEMA_VERSION",
    "INFERENCE_STATUS",
    "MAX_CODE_CHARS",
    "MAX_RECENT_EVENTS",
    "SECRET_KEY_FRAGMENTS",
    "VALID_EXECUTION_STATUSES",
    "ConceptHistorySummary",
    "ConceptStateSnapshot",
    "CounterSnapshot",
    "EvidencePack",
    "EventSnapshot",
    "FailedTestEvidence",
    "FlagSnapshot",
    "LearnerRef",
    "LearnerSnapshot",
    "MisconceptionCandidate",
    "MisconceptionOccurrence",
    "RecurringFlagEvidence",
    "RelevantEventEvidence",
    "is_valid_execution_status",
    "normalize_concept_id",
    "normalize_execution_status",
    "normalize_language",
    "normalize_misconception_id",
]
