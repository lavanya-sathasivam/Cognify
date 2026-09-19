"""COGNIFY verification — typed input/output models (Step 10).

Deterministic, stdlib-only. No DB, no LLM, no code execution, no network,
no filesystem, no environment reads, no clock, no randomness.

Ownership boundaries (read carefully):

- Steps 1-5 own problems, execution, and test evaluation. This package
  CONSUMES already-produced execution outcomes (``PASS`` / ``FAIL`` /
  ``COMPILE_ERROR`` / ``RUNTIME_ERROR`` / ``TIMEOUT``) and never executes
  student code.
- Step 6 owns observed evidence packs; Step 7 owns AI diagnosis.
- Step 8 (Learner Model / ``learner_engine``) owns mastery calculation.
  This package NEVER computes mastery and NEVER writes to the database.
  It only produces a ``VerificationResult`` that Step 8 may later consume
  as evidence (``outcome`` / ``concept_id`` / ``target_misconception_id``
  / ``original_passed`` / ``transfer_passed`` / ``evidence``).
- Step 9 owns adaptive ranking. This package performs NO ranking.

Verification semantics (closed decision table — see ``engine.py``):

- Original retry missing            -> INCOMPLETE (not ready; never guess).
- Original retry non-PASS           -> NOT_IMPROVED (transfer ignored).
- Original PASS + transfer missing  -> INCOMPLETE (never claim verified).
- Original PASS + transfer non-PASS -> SURFACE_FIX.
- Original PASS + transfer PASS     -> VERIFIED_IMPROVED.

``PASS + PASS`` means "verified improvement for this intervention /
concept instance" — explicitly NOT "the student mastered the concept".
Mastery remains owned by Step 8.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

VALID_EXECUTION_OUTCOMES: tuple[str, ...] = (
    "PASS",
    "FAIL",
    "COMPILE_ERROR",
    "RUNTIME_ERROR",
    "TIMEOUT",
)

VALID_VERIFICATION_OUTCOMES: tuple[str, ...] = (
    "VERIFIED_IMPROVED",
    "SURFACE_FIX",
    "NOT_IMPROVED",
    "INCOMPLETE",
)

VALID_REASON_CODES: tuple[str, ...] = (
    "ORIGINAL_RETRY_MISSING",
    "ORIGINAL_RETRY_FAILED",
    "ORIGINAL_RETRY_PASSED_TRANSFER_MISSING",
    "ORIGINAL_RETRY_PASSED_TRANSFER_FAILED",
    "ORIGINAL_AND_TRANSFER_PASSED",
)

# ``INCOMPLETE`` is the canonical "not ready" state. ``NOT_READY`` is
# documented here as a conceptual alias only (the enum stays closed with
# four members so downstream consumers can exhaustively match).
NOT_READY_ALIAS: str = "INCOMPLETE"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_MAX_INTERVENTION_LEVEL_CHARS: int = 200


class ExecutionOutcome(str, Enum):
    """Terminal outcome of one already-executed attempt (consumed, not run)."""

    PASS = "PASS"
    FAIL = "FAIL"
    COMPILE_ERROR = "COMPILE_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIMEOUT = "TIMEOUT"


class VerificationOutcome(str, Enum):
    """Closed verification verdict.

    ``INCOMPLETE`` means "not ready": the original retry (or the transfer
    result needed to distinguish a surface fix) has no result yet, so no
    improvement claim may be made.
    """

    VERIFIED_IMPROVED = "VERIFIED_IMPROVED"
    SURFACE_FIX = "SURFACE_FIX"
    NOT_IMPROVED = "NOT_IMPROVED"
    INCOMPLETE = "INCOMPLETE"


class ReasonCode(str, Enum):
    """Machine-readable reason for a ``VerificationResult`` (deterministic)."""

    ORIGINAL_RETRY_MISSING = "ORIGINAL_RETRY_MISSING"
    ORIGINAL_RETRY_FAILED = "ORIGINAL_RETRY_FAILED"
    ORIGINAL_RETRY_PASSED_TRANSFER_MISSING = (
        "ORIGINAL_RETRY_PASSED_TRANSFER_MISSING"
    )
    ORIGINAL_RETRY_PASSED_TRANSFER_FAILED = (
        "ORIGINAL_RETRY_PASSED_TRANSFER_FAILED"
    )
    ORIGINAL_AND_TRANSFER_PASSED = "ORIGINAL_AND_TRANSFER_PASSED"


# Maps each outcome to its legal reason codes (enforced by VerificationResult).
_REASONS_FOR_OUTCOME: dict[VerificationOutcome, frozenset[ReasonCode]] = {
    VerificationOutcome.INCOMPLETE: frozenset(
        {
            ReasonCode.ORIGINAL_RETRY_MISSING,
            ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_MISSING,
        }
    ),
    VerificationOutcome.NOT_IMPROVED: frozenset(
        {ReasonCode.ORIGINAL_RETRY_FAILED}
    ),
    VerificationOutcome.SURFACE_FIX: frozenset(
        {ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_FAILED}
    ),
    VerificationOutcome.VERIFIED_IMPROVED: frozenset(
        {ReasonCode.ORIGINAL_AND_TRANSFER_PASSED}
    ),
}


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


def _require_optional_id(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string or None.")
    if not _ID_RE.match(text):
        raise ValueError(
            f"{field_name} {value!r} is invalid. "
            "Use letters/digits plus '._-', starting with a letter/digit."
        )
    return text


def normalize_language_track(value: str) -> str:
    """Strip + lower-case; raises unless ``python`` / ``java``."""
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


def normalize_concept_id(value: str) -> str:
    """Strip + upper-case; raises unless a known taxonomy concept."""
    from packages.taxonomy import is_valid_concept

    if not isinstance(value, str):
        raise TypeError(f"concept_id must be str, got {type(value).__name__}.")
    norm = value.strip().upper()
    if not norm or not is_valid_concept(norm):
        raise ValueError(f"Unknown concept_id {value!r}.")
    return norm


def normalize_misconception_id(value: str, concept_id: str) -> str:
    """Strip + upper-case; raises unless known AND belonging to concept."""
    from packages.taxonomy import is_valid_misconception, misconception_belongs_to

    if not isinstance(value, str):
        raise TypeError(
            f"misconception_id must be str, got {type(value).__name__}."
        )
    norm = value.strip().upper()
    if not norm or not is_valid_misconception(norm):
        raise ValueError(f"Unknown misconception_id {value!r}.")
    if not misconception_belongs_to(norm, concept_id):
        raise ValueError(
            f"Misconception {norm!r} does not belong to concept {concept_id!r}."
        )
    return norm


def normalize_execution_outcome(value: object) -> ExecutionOutcome:
    """Coerce ``ExecutionOutcome`` or a case/space-tolerant string to enum."""
    if isinstance(value, ExecutionOutcome):
        return value
    if not isinstance(value, str):
        raise TypeError(
            f"outcome must be str or ExecutionOutcome, got {type(value).__name__}."
        )
    norm = value.strip().upper()
    if norm not in VALID_EXECUTION_OUTCOMES:
        raise ValueError(
            f"Unknown execution outcome {value!r}. "
            f"Use one of {list(VALID_EXECUTION_OUTCOMES)}."
        )
    return ExecutionOutcome(norm)


def normalize_verification_outcome(value: object) -> VerificationOutcome:
    """Coerce ``VerificationOutcome`` or a case/space-tolerant string to enum."""
    if isinstance(value, VerificationOutcome):
        return value
    if not isinstance(value, str):
        raise TypeError(
            "outcome must be str or VerificationOutcome, "
            f"got {type(value).__name__}."
        )
    norm = value.strip().upper()
    if norm not in VALID_VERIFICATION_OUTCOMES:
        raise ValueError(
            f"Unknown verification outcome {value!r}. "
            f"Use one of {list(VALID_VERIFICATION_OUTCOMES)}."
        )
    return VerificationOutcome(norm)


def normalize_reason_code(value: object) -> ReasonCode:
    """Coerce ``ReasonCode`` or a case/space-tolerant string to enum."""
    if isinstance(value, ReasonCode):
        return value
    if not isinstance(value, str):
        raise TypeError(
            f"reason_code must be str or ReasonCode, got {type(value).__name__}."
        )
    norm = value.strip().upper()
    if norm not in VALID_REASON_CODES:
        raise ValueError(
            f"Unknown reason_code {value!r}. "
            f"Use one of {list(VALID_REASON_CODES)}."
        )
    return ReasonCode(norm)


def is_pass(outcome: ExecutionOutcome | None) -> bool:
    """True iff ``outcome`` is exactly ``PASS`` (nothing is inferred)."""
    return outcome is ExecutionOutcome.PASS


# ---------------------------------------------------------------------------
# VerificationAttempt
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VerificationAttempt:
    """One already-produced attempt result consumed by verification.

    Fields:
      - ``problem_id``: which problem was attempted (stored stripped).
      - ``concept_id``: taxonomy concept (stored UPPER, must be known).
      - ``language_track``: ``python`` / ``java`` (stored lower).
      - ``outcome``: terminal execution outcome (``ExecutionOutcome``).
      - ``misconception_id``: optional observed misconception linked to
        this attempt (must belong to ``concept_id`` when supplied).
      - ``is_transfer``: optional marker (``True`` = transfer/isomorphic
        attempt, ``False`` = original retry). ``None`` = unspecified.
      - ``isomorphic_group_id``: optional group linking original + transfer
        variants of the same underlying skill (stored stripped).
    """

    problem_id: str
    concept_id: str
    language_track: str
    outcome: ExecutionOutcome | str
    misconception_id: str | None = None
    is_transfer: bool | None = None
    isomorphic_group_id: str | None = None

    def __post_init__(self) -> None:
        norm_problem = _require_id(self.problem_id, "problem_id")
        norm_concept = normalize_concept_id(self.concept_id)
        norm_track = normalize_language_track(self.language_track)
        norm_outcome = normalize_execution_outcome(self.outcome)
        norm_m: str | None = None
        if self.misconception_id is not None:
            if not isinstance(self.misconception_id, str):
                raise TypeError(
                    "misconception_id must be str or None, "
                    f"got {type(self.misconception_id).__name__}."
                )
            norm_m = normalize_misconception_id(
                self.misconception_id, norm_concept
            )
        if self.is_transfer is not None and not isinstance(
            self.is_transfer, bool
        ):
            raise TypeError(
                f"is_transfer must be bool or None, got {type(self.is_transfer).__name__}."
            )
        norm_iso = _require_optional_id(
            self.isomorphic_group_id, "isomorphic_group_id"
        )
        object.__setattr__(self, "problem_id", norm_problem)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "language_track", norm_track)
        object.__setattr__(self, "outcome", norm_outcome)
        object.__setattr__(self, "misconception_id", norm_m)
        object.__setattr__(self, "isomorphic_group_id", norm_iso)

    @property
    def passed(self) -> bool:
        """True iff this attempt's outcome is ``PASS``."""
        assert isinstance(self.outcome, ExecutionOutcome)
        return self.outcome is ExecutionOutcome.PASS

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping."""
        assert isinstance(self.outcome, ExecutionOutcome)
        return {
            "problem_id": self.problem_id,
            "concept_id": self.concept_id,
            "language_track": self.language_track,
            "outcome": self.outcome.value,
            "misconception_id": self.misconception_id,
            "is_transfer": self.is_transfer,
            "isomorphic_group_id": self.isomorphic_group_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationAttempt":
        if not isinstance(data, dict):
            raise TypeError(
                f"VerificationAttempt.from_dict needs a dict, got {type(data).__name__}."
            )
        required = ("problem_id", "concept_id", "language_track", "outcome")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(
                f"VerificationAttempt dict missing keys: {missing}."
            )
        extra = [k for k in data if k not in (*required, "misconception_id", "is_transfer", "isomorphic_group_id")]
        if extra:
            raise ValueError(
                f"VerificationAttempt dict has unexpected keys: {extra}."
            )
        return cls(
            problem_id=data["problem_id"],
            concept_id=data["concept_id"],
            language_track=data["language_track"],
            outcome=data["outcome"],
            misconception_id=data.get("misconception_id"),
            is_transfer=data.get("is_transfer"),
            isomorphic_group_id=data.get("isomorphic_group_id"),
        )


# ---------------------------------------------------------------------------
# VerificationContext
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VerificationContext:
    """Everything ``verify_improvement`` needs (pure input, no side effects).

    Fields:
      - ``original_problem_id`` / ``transfer_problem_id``: problem identities.
        ``transfer_problem_id`` may be ``None`` when no transfer problem has
        been assigned yet (then the verdict can be at most INCOMPLETE).
      - ``concept_id`` / ``language_track``: shared scope for both attempts.
      - ``target_misconception_id``: intervention target (optional; when
        supplied it must belong to ``concept_id`` and is preserved verbatim
        into the result for Step 8).
      - ``intervention_level``: opaque label for the intervention that
        preceded the retry (optional, e.g. ``"hint-L2"``). Stored stripped;
        never influences the verdict (verification is outcome-only; no
        improvement is inferred from confidence or hint levels).
      - ``original_retry`` / ``transfer``: already-produced attempt results
        (``None`` = no result yet).
      - ``isomorphic_group_id``: optional group that must be consistent
        across every place it is supplied (context + attempts).

    Cross-field validation (all failures raise ``TypeError``/``ValueError``):
      - transfer problem (when known) must differ from the original problem.
      - each supplied attempt must agree with the context on problem id,
        concept, and language track (no cross-language / cross-concept
        mixing, no contradictory identities).
      - ``original_retry`` must not be flagged ``is_transfer=True``;
        ``transfer`` must not be flagged ``is_transfer=False``.
      - every supplied ``isomorphic_group_id`` must be identical.
    """

    original_problem_id: str
    concept_id: str
    language_track: str
    transfer_problem_id: str | None = None
    target_misconception_id: str | None = None
    intervention_level: str | None = None
    original_retry: VerificationAttempt | None = None
    transfer: VerificationAttempt | None = None
    isomorphic_group_id: str | None = None

    def __post_init__(self) -> None:
        norm_original = _require_id(self.original_problem_id, "original_problem_id")
        norm_transfer_pid = _require_optional_id(
            self.transfer_problem_id, "transfer_problem_id"
        )
        norm_concept = normalize_concept_id(self.concept_id)
        norm_track = normalize_language_track(self.language_track)

        if (
            norm_transfer_pid is not None
            and norm_transfer_pid == norm_original
        ):
            raise ValueError(
                f"transfer_problem_id {norm_transfer_pid!r} must differ from "
                f"original_problem_id {norm_original!r}."
            )

        norm_target: str | None = None
        if self.target_misconception_id is not None:
            if not isinstance(self.target_misconception_id, str):
                raise TypeError(
                    "target_misconception_id must be str or None, "
                    f"got {type(self.target_misconception_id).__name__}."
                )
            norm_target = normalize_misconception_id(
                self.target_misconception_id, norm_concept
            )

        norm_level: str | None = None
        if self.intervention_level is not None:
            if not isinstance(self.intervention_level, str):
                raise TypeError(
                    "intervention_level must be str or None, "
                    f"got {type(self.intervention_level).__name__}."
                )
            norm_level = self.intervention_level.strip()
            if not norm_level:
                raise ValueError(
                    "intervention_level must be a non-empty string or None."
                )
            if len(norm_level) > _MAX_INTERVENTION_LEVEL_CHARS:
                raise ValueError(
                    "intervention_level exceeds "
                    f"{_MAX_INTERVENTION_LEVEL_CHARS} characters."
                )

        if self.original_retry is not None and not isinstance(
            self.original_retry, VerificationAttempt
        ):
            raise TypeError(
                "original_retry must be VerificationAttempt or None, "
                f"got {type(self.original_retry).__name__}."
            )
        if self.transfer is not None and not isinstance(
            self.transfer, VerificationAttempt
        ):
            raise TypeError(
                "transfer must be VerificationAttempt or None, "
                f"got {type(self.transfer).__name__}."
            )

        norm_iso = _require_optional_id(
            self.isomorphic_group_id, "isomorphic_group_id"
        )

        # -- per-attempt agreement --------------------------------------
        if self.original_retry is not None:
            attempt = self.original_retry
            if attempt.problem_id != norm_original:
                raise ValueError(
                    f"original_retry.problem_id {attempt.problem_id!r} does not "
                    f"match original_problem_id {norm_original!r}."
                )
            if attempt.concept_id != norm_concept:
                raise ValueError(
                    f"original_retry.concept_id {attempt.concept_id!r} does not "
                    f"match context concept {norm_concept!r} "
                    "(no cross-concept mixing)."
                )
            if attempt.language_track != norm_track:
                raise ValueError(
                    f"original_retry track {attempt.language_track!r} does not "
                    f"match context track {norm_track!r} "
                    "(no cross-language mixing)."
                )
            if attempt.is_transfer is True:
                raise ValueError(
                    "original_retry.is_transfer must not be True "
                    "(the original retry is not a transfer attempt)."
                )

        if self.transfer is not None:
            attempt = self.transfer
            if norm_transfer_pid is None:
                raise ValueError(
                    "transfer result supplied without transfer_problem_id; "
                    "set transfer_problem_id to identify the transfer problem."
                )
            if attempt.problem_id != norm_transfer_pid:
                raise ValueError(
                    f"transfer.problem_id {attempt.problem_id!r} does not match "
                    f"transfer_problem_id {norm_transfer_pid!r}."
                )
            if attempt.concept_id != norm_concept:
                raise ValueError(
                    f"transfer.concept_id {attempt.concept_id!r} does not match "
                    f"context concept {norm_concept!r} "
                    "(no cross-concept mixing)."
                )
            if attempt.language_track != norm_track:
                raise ValueError(
                    f"transfer track {attempt.language_track!r} does not match "
                    f"context track {norm_track!r} (no cross-language mixing)."
                )
            if attempt.is_transfer is False:
                raise ValueError(
                    "transfer.is_transfer must not be False "
                    "(the transfer result must be a transfer attempt)."
                )

        # -- isomorphic-group consistency --------------------------------
        supplied_iso: list[str] = []
        if norm_iso is not None:
            supplied_iso.append(norm_iso)
        if self.original_retry is not None and self.original_retry.isomorphic_group_id is not None:
            supplied_iso.append(self.original_retry.isomorphic_group_id)
        if self.transfer is not None and self.transfer.isomorphic_group_id is not None:
            supplied_iso.append(self.transfer.isomorphic_group_id)
        if len(set(supplied_iso)) > 1:
            raise ValueError(
                f"Contradictory isomorphic_group_id values: {supplied_iso!r}; "
                "every supplied group id must be identical."
            )

        object.__setattr__(self, "original_problem_id", norm_original)
        object.__setattr__(self, "transfer_problem_id", norm_transfer_pid)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "language_track", norm_track)
        object.__setattr__(self, "target_misconception_id", norm_target)
        object.__setattr__(self, "intervention_level", norm_level)
        object.__setattr__(self, "isomorphic_group_id", norm_iso)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping."""
        return {
            "original_problem_id": self.original_problem_id,
            "transfer_problem_id": self.transfer_problem_id,
            "concept_id": self.concept_id,
            "language_track": self.language_track,
            "target_misconception_id": self.target_misconception_id,
            "intervention_level": self.intervention_level,
            "original_retry": (
                self.original_retry.to_dict()
                if self.original_retry is not None
                else None
            ),
            "transfer": (
                self.transfer.to_dict() if self.transfer is not None else None
            ),
            "isomorphic_group_id": self.isomorphic_group_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationContext":
        if not isinstance(data, dict):
            raise TypeError(
                f"VerificationContext.from_dict needs a dict, got {type(data).__name__}."
            )
        required = ("original_problem_id", "concept_id", "language_track")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(
                f"VerificationContext dict missing keys: {missing}."
            )
        allowed = {
            "original_problem_id",
            "transfer_problem_id",
            "concept_id",
            "language_track",
            "target_misconception_id",
            "intervention_level",
            "original_retry",
            "transfer",
            "isomorphic_group_id",
        }
        extra = [k for k in data if k not in allowed]
        if extra:
            raise ValueError(
                f"VerificationContext dict has unexpected keys: {extra}."
            )
        raw_original = data.get("original_retry")
        raw_transfer = data.get("transfer")
        return cls(
            original_problem_id=data["original_problem_id"],
            concept_id=data["concept_id"],
            language_track=data["language_track"],
            transfer_problem_id=data.get("transfer_problem_id"),
            target_misconception_id=data.get("target_misconception_id"),
            intervention_level=data.get("intervention_level"),
            original_retry=(
                VerificationAttempt.from_dict(raw_original)
                if isinstance(raw_original, dict)
                else raw_original
            ),
            transfer=(
                VerificationAttempt.from_dict(raw_transfer)
                if isinstance(raw_transfer, dict)
                else raw_transfer
            ),
            isomorphic_group_id=data.get("isomorphic_group_id"),
        )


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VerificationResult:
    """Deterministic verification verdict + evidence for Step 8.

    This is EVIDENCE, not mastery: Step 8 (``learner_engine``) owns all
    mastery calculation and may consume ``outcome`` / ``concept_id`` /
    ``target_misconception_id`` / ``original_passed`` / ``transfer_passed``
    / ``evidence`` in a future integration. This package never writes to
    the database.
    """

    outcome: VerificationOutcome | str
    reason_code: ReasonCode | str
    reason: str
    concept_id: str
    language_track: str
    original_problem_id: str
    transfer_problem_id: str | None
    target_misconception_id: str | None
    original_passed: bool
    transfer_passed: bool
    evidence: tuple[str, ...] | list[str]
    original_outcome: ExecutionOutcome | str | None = None
    transfer_outcome: ExecutionOutcome | str | None = None
    intervention_level: str | None = None
    isomorphic_group_id: str | None = None

    def __post_init__(self) -> None:
        norm_outcome = normalize_verification_outcome(self.outcome)
        norm_reason = normalize_reason_code(self.reason_code)
        if norm_reason not in _REASONS_FOR_OUTCOME[norm_outcome]:
            raise ValueError(
                f"reason_code {norm_reason.value!r} is inconsistent with "
                f"outcome {norm_outcome.value!r}."
            )
        if not isinstance(self.reason, str):
            raise TypeError(
                f"reason must be str, got {type(self.reason).__name__}."
            )
        reason_text = self.reason.strip()
        if not 10 <= len(reason_text) <= 500:
            raise ValueError(
                "reason must be 10..500 chars (concise deterministic "
                f"explanation), got {len(reason_text)}."
            )
        norm_concept = normalize_concept_id(self.concept_id)
        norm_track = normalize_language_track(self.language_track)
        norm_original = _require_id(self.original_problem_id, "original_problem_id")
        norm_transfer_pid = _require_optional_id(
            self.transfer_problem_id, "transfer_problem_id"
        )
        if norm_transfer_pid is not None and norm_transfer_pid == norm_original:
            raise ValueError(
                "transfer_problem_id must differ from original_problem_id."
            )
        norm_target: str | None = None
        if self.target_misconception_id is not None:
            if not isinstance(self.target_misconception_id, str):
                raise TypeError(
                    "target_misconception_id must be str or None, "
                    f"got {type(self.target_misconception_id).__name__}."
                )
            norm_target = normalize_misconception_id(
                self.target_misconception_id, norm_concept
            )
        if not isinstance(self.original_passed, bool):
            raise TypeError(
                f"original_passed must be bool, got {type(self.original_passed).__name__}."
            )
        if not isinstance(self.transfer_passed, bool):
            raise TypeError(
                f"transfer_passed must be bool, got {type(self.transfer_passed).__name__}."
            )
        norm_original_outcome: ExecutionOutcome | None = None
        if self.original_outcome is not None:
            norm_original_outcome = normalize_execution_outcome(
                self.original_outcome
            )
        norm_transfer_outcome: ExecutionOutcome | None = None
        if self.transfer_outcome is not None:
            norm_transfer_outcome = normalize_execution_outcome(
                self.transfer_outcome
            )
        if self.original_passed != is_pass(norm_original_outcome):
            raise ValueError(
                "original_passed disagrees with original_outcome "
                f"({norm_original_outcome!r})."
            )
        if self.transfer_passed != is_pass(norm_transfer_outcome):
            raise ValueError(
                "transfer_passed disagrees with transfer_outcome "
                f"({norm_transfer_outcome!r})."
            )
        if not isinstance(self.evidence, (list, tuple)):
            raise TypeError(
                f"evidence must be a list/tuple of str, got {type(self.evidence).__name__}."
            )
        evidence = tuple(self.evidence)
        if len(evidence) == 0:
            raise ValueError("evidence must contain at least one entry.")
        for entry in evidence:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("evidence entries must be non-empty strings.")
        norm_level: str | None = None
        if self.intervention_level is not None:
            if not isinstance(self.intervention_level, str):
                raise TypeError(
                    "intervention_level must be str or None, "
                    f"got {type(self.intervention_level).__name__}."
                )
            norm_level = self.intervention_level.strip()
            if not norm_level:
                raise ValueError(
                    "intervention_level must be a non-empty string or None."
                )
        norm_iso = _require_optional_id(
            self.isomorphic_group_id, "isomorphic_group_id"
        )

        object.__setattr__(self, "outcome", norm_outcome)
        object.__setattr__(self, "reason_code", norm_reason)
        object.__setattr__(self, "reason", reason_text)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "language_track", norm_track)
        object.__setattr__(self, "original_problem_id", norm_original)
        object.__setattr__(self, "transfer_problem_id", norm_transfer_pid)
        object.__setattr__(self, "target_misconception_id", norm_target)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "original_outcome", norm_original_outcome)
        object.__setattr__(self, "transfer_outcome", norm_transfer_outcome)
        object.__setattr__(self, "intervention_level", norm_level)
        object.__setattr__(self, "isomorphic_group_id", norm_iso)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping for Step 8 consumers."""
        assert isinstance(self.outcome, VerificationOutcome)
        assert isinstance(self.reason_code, ReasonCode)
        return {
            "outcome": self.outcome.value,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "concept_id": self.concept_id,
            "language_track": self.language_track,
            "original_problem_id": self.original_problem_id,
            "transfer_problem_id": self.transfer_problem_id,
            "target_misconception_id": self.target_misconception_id,
            "original_passed": self.original_passed,
            "transfer_passed": self.transfer_passed,
            "evidence": list(self.evidence),
            "original_outcome": (
                self.original_outcome.value
                if isinstance(self.original_outcome, ExecutionOutcome)
                else None
            ),
            "transfer_outcome": (
                self.transfer_outcome.value
                if isinstance(self.transfer_outcome, ExecutionOutcome)
                else None
            ),
            "intervention_level": self.intervention_level,
            "isomorphic_group_id": self.isomorphic_group_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationResult":
        if not isinstance(data, dict):
            raise TypeError(
                f"VerificationResult.from_dict needs a dict, got {type(data).__name__}."
            )
        required = (
            "outcome",
            "reason_code",
            "reason",
            "concept_id",
            "language_track",
            "original_problem_id",
            "target_misconception_id",
            "original_passed",
            "transfer_passed",
            "evidence",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(
                f"VerificationResult dict missing keys: {missing}."
            )
        allowed = set(required) | {
            "transfer_problem_id",
            "original_outcome",
            "transfer_outcome",
            "intervention_level",
            "isomorphic_group_id",
        }
        extra = [k for k in data if k not in allowed]
        if extra:
            raise ValueError(
                f"VerificationResult dict has unexpected keys: {extra}."
            )
        return cls(
            outcome=data["outcome"],
            reason_code=data["reason_code"],
            reason=data["reason"],
            concept_id=data["concept_id"],
            language_track=data["language_track"],
            original_problem_id=data["original_problem_id"],
            transfer_problem_id=data.get("transfer_problem_id"),
            target_misconception_id=data["target_misconception_id"],
            original_passed=data["original_passed"],
            transfer_passed=data["transfer_passed"],
            evidence=data["evidence"],
            original_outcome=data.get("original_outcome"),
            transfer_outcome=data.get("transfer_outcome"),
            intervention_level=data.get("intervention_level"),
            isomorphic_group_id=data.get("isomorphic_group_id"),
        )


__all__ = [
    "NOT_READY_ALIAS",
    "VALID_EXECUTION_OUTCOMES",
    "VALID_REASON_CODES",
    "VALID_VERIFICATION_OUTCOMES",
    "ExecutionOutcome",
    "ReasonCode",
    "VerificationAttempt",
    "VerificationContext",
    "VerificationOutcome",
    "VerificationResult",
    "is_pass",
    "normalize_concept_id",
    "normalize_execution_outcome",
    "normalize_language_track",
    "normalize_misconception_id",
    "normalize_reason_code",
    "normalize_verification_outcome",
]
