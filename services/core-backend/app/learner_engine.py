"""COGNIFY core-backend — learner engine (Step 8: Learner Model + Mastery).

Ownership:
- ONLY core-backend mutates learner state (concept states, counters, flags,
  events). The AI service never writes here: it receives read-only
  EvidencePacks over HTTP and returns diagnoses; this engine consumes those
  diagnoses plus execution evidence to update mastery.
- Mastery math itself lives in ``packages.mastery`` (pure, deterministic,
  stdlib-only). This module owns DB reads/writes, language-track isolation,
  recurring-weakness bookkeeping, and the append-only history that explains
  "why is mastery X?".

Language-track isolation:
- Every mutation is scoped via ``(user_id, journey_id)``; journeys carry the
  ``language_track`` (python/java) and repositories verify
  ``journey.user_id == user_id``. PYTHON and JAVA journeys are separate rows,
  so their states, counters, flags, and events never mix. Transitions record
  the journey's ``language_track`` explicitly.

Event taxonomy (append-only ``learner_events``):
- ``attempt``: one submission (metadata: problem_id, isomorphic_group_id,
  variant_role, passed/success, execution_status, misconception_id or None,
  hint_used, is_transfer, evidence_refs).
- ``diagnosis``: AI diagnosis consumed (metadata: problem_id,
  misconception_id, confidence, evidence_refs, execution_status).
- ``mastery_transition``: auditable mastery delta (metadata: problem_id,
  previous_mastery, new_mastery, delta, reason, evidence_refs,
  execution_status, passed, hint_used, is_transfer, band_before/after).
- ``recurring_detected`` / ``recurring_cleared``: flag transitions
  (metadata: misconception_id, reason, occurrence/total counts).

Initial state: a new (journey, concept) starts at mastery 0.20 / band
``novice`` / trend ``unknown`` with zero counts (DB model defaults of 0.0
are normalized to 0.20 on first ``ensure`` so Step 4 storage behavior is
preserved for raw repository use).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from packages import mastery as mastery_pkg
from packages.evidence.models import (
    ConceptStateSnapshot,
    CounterSnapshot,
    EventSnapshot,
    FlagSnapshot,
    LearnerSnapshot,
)
from packages.mastery import formula as mastery_formula
from packages.mastery import weakness as weakness_rules
from packages.problem_schema.models import normalize_variant_role

from . import repositories
from .models import Journey, LearnerConceptState

INITIAL_MASTERY: float = mastery_formula.INITIAL_MASTERY

EVENT_ATTEMPT: str = "attempt"
EVENT_DIAGNOSIS: str = "diagnosis"
EVENT_MASTERY_TRANSITION: str = "mastery_transition"
EVENT_RECURRING_DETECTED: str = "recurring_detected"
EVENT_RECURRING_CLEARED: str = "recurring_cleared"

_VALID_VARIANT_ROLES: tuple[str, ...] = ("canonical", "transfer", "remedial")


# ---------------------------------------------------------------------------
# Small validators
# ---------------------------------------------------------------------------
def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool, got {type(value).__name__}.")
    return value


def _validate_evidence_refs(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"evidence_refs must be a list/tuple of str, got {type(value).__name__}."
        )
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("evidence_refs entries must be non-empty strings.")
        refs.append(item.strip())
    if len(set(refs)) != len(refs):
        raise ValueError(f"evidence_refs contains duplicates: {refs!r}.")
    return refs


def _validate_confidence(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"diagnostic_confidence must be a number or None, "
            f"got {type(value).__name__}."
        )
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(
            f"diagnostic_confidence must be in [0, 1], got {value!r}."
        )
    return number


def _get_journey(session: Session, user_id: int, journey_id: int) -> Journey:
    journey = session.get(Journey, journey_id)
    if journey is None:
        raise ValueError(f"Unknown journey_id {journey_id!r}.")
    if journey.user_id != user_id:
        raise ValueError(
            f"Journey {journey_id!r} belongs to user {journey.user_id!r}, "
            f"not user {user_id!r} (tracks must not cross)."
        )
    return journey


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        return str(value)
    return value.isoformat()


# ---------------------------------------------------------------------------
# Concept-state lifecycle
# ---------------------------------------------------------------------------
def ensure_concept_state(
    session: Session, user_id: int, journey_id: int, concept_id: str
) -> LearnerConceptState:
    """Get-or-create the concept row, normalizing new rows to 0.20/novice.

    Raw ``repositories.get_or_create_concept_state`` keeps its Step 4
    defaults (0.0); this engine upgrades freshly created rows (or legacy
    untouched rows with attempt_count == 0 and mastery == 0.0) to the Step 8
    initial mastery of 0.20 / novice / unknown so the first
    ``compute_mastery_update`` starts from the spec'd prior.
    """
    norm_concept = repositories.normalize_concept_id(concept_id)
    _get_journey(session, user_id, journey_id)
    state, created = repositories.get_or_create_concept_state(
        session, user_id, journey_id, norm_concept
    )
    if created or (state.attempt_count == 0 and float(state.mastery) == 0.0):
        repositories.update_concept_state(
            session,
            journey_id,
            norm_concept,
            mastery=INITIAL_MASTERY,
            current_band=mastery_formula.mastery_band(INITIAL_MASTERY),
            trend="unknown",
        )
        session.flush()
        session.refresh(state)
    return state


# ---------------------------------------------------------------------------
# Attempt-history helpers (derived, never stored redundantly)
# ---------------------------------------------------------------------------
def _attempt_events(
    session: Session, journey_id: int, concept_id: str, limit: int | None = None
) -> list[Any]:
    """Attempt events for (journey, concept), oldest -> newest."""
    norm_concept = repositories.normalize_concept_id(concept_id)
    events = repositories.list_events_for_journey(
        session, journey_id, event_type=EVENT_ATTEMPT, concept_id=norm_concept
    )
    if limit is not None:
        if type(limit) is not int or limit < 1:
            raise ValueError(f"limit must be a positive int, got {limit!r}.")
        events = events[-limit:]
    return events


def _attempt_histories(
    session: Session, journey_id: int, concept_id: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """Plain-data attempt summaries, oldest -> newest.

    Each entry: {passed, misconception_id, problem_id, isomorphic_group_id,
    execution_status, hint_used, is_transfer}.
    """
    histories: list[dict[str, Any]] = []
    for event in _attempt_events(session, journey_id, concept_id, limit=limit):
        meta = dict(event.event_metadata or {})
        passed = meta.get("passed", meta.get("success", False))
        histories.append(
            {
                "passed": bool(passed),
                "misconception_id": event.misconception_id,
                "problem_id": meta.get("problem_id"),
                "isomorphic_group_id": meta.get("isomorphic_group_id"),
                "execution_status": meta.get("execution_status"),
                "hint_used": bool(meta.get("hint_used", False)),
                "is_transfer": bool(meta.get("is_transfer", False)),
                "event_id": event.id,
            }
        )
    return histories


def _prior_recent_pass_rate(
    session: Session, journey_id: int, concept_id: str
) -> float:
    histories = _attempt_histories(session, journey_id, concept_id, limit=5)
    if not histories:
        return 0.5
    outcomes = [h["passed"] for h in histories[-5:]]
    return round(sum(1 for ok in outcomes if ok) / len(outcomes), 4)


# ---------------------------------------------------------------------------
# Read views (no writes)
# ---------------------------------------------------------------------------
def get_concept_view(
    session: Session, journey_id: int, concept_id: str
) -> dict[str, Any]:
    """Full learner-concept snapshot including derived fields.

    Keys: user_id, journey_id, language_track, concept_id, mastery, band,
    attempt_count, pass_count, fail_count, recent_performance
    ({last_5, pass_rate}), trend, active_misconception_ids (sorted),
    hint_dependence, hint_count, transfer_success_rate, transfer_attempts,
    transfer_successes, last_attempted_at (ISO or None).
    """
    norm_concept = repositories.normalize_concept_id(concept_id)
    journey = session.get(Journey, journey_id)
    if journey is None:
        raise ValueError(f"Unknown journey_id {journey_id!r}.")
    state = repositories.get_concept_state(session, journey_id, norm_concept)
    if state is None:
        mastery = INITIAL_MASTERY
        band = mastery_formula.mastery_band(mastery)
        return {
            "user_id": journey.user_id,
            "journey_id": journey_id,
            "language_track": journey.language_track,
            "concept_id": norm_concept,
            "mastery": mastery,
            "band": band,
            "attempt_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "recent_performance": {"last_5": [], "pass_rate": 0.0},
            "trend": "unknown",
            "active_misconception_ids": [],
            "hint_dependence": 0.0,
            "hint_count": 0,
            "transfer_success_rate": 0.0,
            "transfer_attempts": 0,
            "transfer_successes": 0,
            "last_attempted_at": None,
        }
    histories = _attempt_histories(session, journey_id, norm_concept, limit=5)
    last_5 = [h["passed"] for h in histories]
    pass_rate = (
        round(sum(1 for ok in last_5 if ok) / len(last_5), 4) if last_5 else 0.0
    )
    counters = [
        c
        for c in repositories.list_counters_for_journey(session, journey_id)
        if c.concept_id == norm_concept and c.active
    ]
    active_ids = sorted(c.misconception_id for c in counters)
    # Last attempted: newest attempt event, else row updated_at.
    attempt_events = _attempt_events(session, journey_id, norm_concept)
    last_at = (
        _iso_or_none(attempt_events[-1].created_at)
        if attempt_events
        else _iso_or_none(state.updated_at)
    )
    fail_count = max(0, state.attempt_count - state.successful_attempts)
    return {
        "user_id": state.user_id,
        "journey_id": journey_id,
        "language_track": journey.language_track,
        "concept_id": norm_concept,
        "mastery": float(state.mastery),
        "band": state.current_band,
        "attempt_count": state.attempt_count,
        "pass_count": state.successful_attempts,
        "fail_count": fail_count,
        "recent_performance": {"last_5": last_5, "pass_rate": pass_rate},
        "trend": state.trend,
        "active_misconception_ids": active_ids,
        "hint_dependence": mastery_formula.hint_dependence_rate(
            state.hint_count, state.attempt_count
        ),
        "hint_count": state.hint_count,
        "transfer_success_rate": mastery_formula.transfer_success_rate(
            state.transfer_successes, state.transfer_attempts
        ),
        "transfer_attempts": state.transfer_attempts,
        "transfer_successes": state.transfer_successes,
        "last_attempted_at": last_at,
    }


def get_misconception_view(
    session: Session, journey_id: int, concept_id: str, misconception_id: str
) -> dict[str, Any]:
    """Per-misconception tracking view (counts + recency + improvement)."""
    norm_concept = repositories.normalize_concept_id(concept_id)
    norm_m = repositories.normalize_misconception_id(misconception_id)
    if not mastery_pkg or True:
        from packages.taxonomy import misconception_belongs_to as _belongs

        if not _belongs(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept "
                f"{norm_concept!r}."
            )
    journey = session.get(Journey, journey_id)
    if journey is None:
        raise ValueError(f"Unknown journey_id {journey_id!r}.")
    counter = repositories.get_counter(session, journey_id, norm_concept, norm_m)
    histories = _attempt_histories(session, journey_id, norm_concept, limit=None)
    mids: list[str | None] = [h["misconception_id"] for h in histories]
    recent_count = weakness_rules.recent_occurrence_count(
        mids, norm_m, window=weakness_rules.RECENT_WINDOW
    )
    # R3: same misconception across 2+ isomorphic variants, i.e. >= 2
    # distinct problem_ids sharing one isomorphic_group_id. Bare distinct
    # problem_ids from different groups must NOT fire R3.
    occurrences = [
        (h["problem_id"], h["isomorphic_group_id"])
        for h in histories
        if h["misconception_id"] == norm_m
    ]
    n_variants = weakness_rules.isomorphic_variant_count(occurrences)
    occurrence = counter.occurrence_count if counter is not None else 0
    is_rec, rec_reason = weakness_rules.check_recurring(
        occurrence, recent_count, n_variants
    )
    # Improvement uses trailing window of (passed, misconception_id).
    pairs = [(h["passed"], h["misconception_id"]) for h in histories]
    is_improving = (
        weakness_rules.has_improved(pairs, norm_m) if pairs else False
    )
    flag = repositories.get_flag(session, journey_id, norm_concept, norm_m)
    return {
        "misconception_id": norm_m,
        "concept_id": norm_concept,
        "occurrence_count": occurrence,
        "recent_count": recent_count,
        "recent_window": weakness_rules.RECENT_WINDOW,
        "distinct_variant_count": n_variants,
        "last_seen_at": _iso_or_none(counter.last_seen_at) if counter else None,
        "active": bool(counter.active) if counter is not None else False,
        "is_recurring": bool(flag.is_recurring) if flag is not None else is_rec,
        "recurring_reason": (flag.reason if flag and flag.reason else rec_reason),
        "is_improving": is_improving,
        "resolved": bool(is_improving and not (flag.is_recurring if flag else is_rec)),
    }


# ---------------------------------------------------------------------------
# Main mutation: record one attempt
# ---------------------------------------------------------------------------
def record_attempt(
    session: Session,
    *,
    user_id: int,
    journey_id: int,
    concept_id: str,
    problem_id: str,
    isomorphic_group_id: str,
    variant_role: str,
    passed: bool,
    execution_status: str,
    diagnosed_misconception_id: str | None = None,
    diagnostic_confidence: float | None = None,
    hint_used: bool = False,
    evidence_refs: list[str] | tuple[str, ...] | None = None,
    is_transfer: bool | None = None,
) -> dict[str, Any]:
    """Record one submission's evidence + diagnosis and update mastery.

    Deterministic given identical inputs against an identical DB state
    (timestamps excluded): mastery deltas come from
    ``packages.mastery.formula.compute_mastery_update``; recurring flags
    come from ``packages.mastery.weakness.check_recurring``.

    Returns:
        ``{"transition": {...}, "concept_view": {...},
        "misconception_view": {...} | None, "improved_ids": [...]}``
        where ``transition`` holds concept_id, language_track,
        previous_mastery, new_mastery, delta, reason, evidence_refs,
        timestamp, attempt_number, band_before/after, trend, passed,
        execution_status, hint_used, is_transfer, problem_id.
    """
    norm_concept = repositories.normalize_concept_id(concept_id)
    norm_problem = _require_non_empty_str(problem_id, "problem_id")
    norm_iso = _require_non_empty_str(isomorphic_group_id, "isomorphic_group_id")
    norm_role = normalize_variant_role(variant_role)
    _require_bool(passed, "passed")
    _require_bool(hint_used, "hint_used")
    refs = _validate_evidence_refs(evidence_refs)
    confidence = _validate_confidence(diagnostic_confidence)
    if not isinstance(execution_status, str):
        raise TypeError(
            f"execution_status must be str, got {type(execution_status).__name__}."
        )
    status_norm = execution_status.strip().upper()
    # Validates status vocabulary (raises on unknown).
    mastery_formula.severity_for_status(status_norm)
    if passed and status_norm != "PASSED":
        raise ValueError(
            f"passed=True disagrees with execution_status {status_norm!r}."
        )
    if not passed and status_norm == "PASSED":
        raise ValueError("passed=False disagrees with execution_status 'PASSED'.")

    norm_m: str | None = None
    if diagnosed_misconception_id is not None:
        norm_m = repositories.normalize_misconception_id(
            diagnosed_misconception_id
        )
        from packages.taxonomy import misconception_belongs_to as _belongs

        if not _belongs(norm_m, norm_concept):
            raise ValueError(
                f"Misconception {norm_m!r} does not belong to concept "
                f"{norm_concept!r}."
            )

    journey = _get_journey(session, user_id, journey_id)
    language_track = journey.language_track

    resolved_transfer = (
        bool(is_transfer)
        if is_transfer is not None
        else mastery_formula.is_transfer_variant(norm_role)
    )
    if is_transfer is not None and not isinstance(is_transfer, bool):
        raise TypeError(
            f"is_transfer must be bool or None, got {type(is_transfer).__name__}."
        )

    state = ensure_concept_state(session, user_id, journey_id, norm_concept)
    previous_mastery = float(state.mastery)
    band_before = state.current_band

    prior_rate = _prior_recent_pass_rate(session, journey_id, norm_concept)
    new_mastery, delta, reason = mastery_formula.compute_mastery_update(
        previous_mastery,
        passed,
        status_norm,
        hint_used,
        resolved_transfer,
        prior_rate,
    )
    band_after = mastery_formula.mastery_band(new_mastery)

    # Trend includes the current outcome.
    prior_histories = _attempt_histories(session, journey_id, norm_concept)
    new_outcomes = [h["passed"] for h in prior_histories] + [passed]
    new_trend = mastery_formula.compute_trend(new_outcomes)

    new_attempt_count = state.attempt_count + 1
    new_successful = state.successful_attempts + (1 if passed else 0)
    new_hint_count = state.hint_count + (1 if hint_used else 0)
    new_transfer_attempts = state.transfer_attempts + (1 if resolved_transfer else 0)
    new_transfer_successes = state.transfer_successes + (
        1 if (resolved_transfer and passed) else 0
    )

    repositories.update_concept_state(
        session,
        journey_id,
        norm_concept,
        mastery=new_mastery,
        attempt_count=new_attempt_count,
        successful_attempts=new_successful,
        current_band=band_after,
        trend=new_trend,
        hint_count=new_hint_count,
        transfer_attempts=new_transfer_attempts,
        transfer_successes=new_transfer_successes,
    )
    session.flush()

    # -- misconception counters -------------------------------------------
    if norm_m is not None:
        repositories.increment_counter(
            session, user_id, journey_id, norm_concept, norm_m, increment=1
        )
        counter = repositories.get_counter(
            session, journey_id, norm_concept, norm_m
        )
        assert counter is not None
        if not counter.active:
            repositories.set_counter_active(
                session, journey_id, norm_concept, norm_m, True
            )
    else:
        counter = None

    # -- recurring evaluation for the diagnosed misconception -------------
    recurring_now: bool | None = None
    recurring_reason: str | None = None
    if norm_m is not None:
        all_histories = _attempt_histories(session, journey_id, norm_concept)
        # Histories do not yet include the CURRENT attempt event (created
        # below), so append the current occurrence explicitly for the
        # trailing-window / variant counts.
        mids_with_current = [h["misconception_id"] for h in all_histories] + [norm_m]
        recent_count = weakness_rules.recent_occurrence_count(
            mids_with_current, norm_m
        )
        live_counter = repositories.get_counter(
            session, journey_id, norm_concept, norm_m
        )
        assert live_counter is not None
        # R3 (write path): include the CURRENT attempt's
        # (problem_id, isomorphic_group_id) alongside prior histories so the
        # decision reflects the state after this attempt. Grouping is by
        # isomorphic_group_id: only >= 2 distinct problems within ONE group
        # fires R3.
        occurrences = [
            (h["problem_id"], h["isomorphic_group_id"])
            for h in all_histories
            if h["misconception_id"] == norm_m
        ] + [(norm_problem, norm_iso)]
        n_variants = weakness_rules.isomorphic_variant_count(occurrences)
        recurring_now, recurring_reason = weakness_rules.check_recurring(
            live_counter.occurrence_count, recent_count, n_variants
        )
        prev_flag = repositories.get_flag(
            session, journey_id, norm_concept, norm_m
        )
        was_recurring = bool(prev_flag.is_recurring) if prev_flag else False
        repositories.set_recurring_flag(
            session,
            user_id,
            journey_id,
            norm_concept,
            norm_m,
            recurring_now,
            reason=recurring_reason,
        )
        if recurring_now and not was_recurring:
            repositories.create_event(
                session,
                user_id,
                journey_id,
                EVENT_RECURRING_DETECTED,
                norm_concept,
                misconception_id=norm_m,
                metadata={
                    "problem_id": norm_problem,
                    "isomorphic_group_id": norm_iso,
                    "reason": recurring_reason,
                    "occurrence_count": live_counter.occurrence_count,
                    "recent_count": recent_count,
                    "distinct_variant_count": n_variants,
                },
            )

    # -- improvement sweep over all active counters for the concept --------
    # Re-read histories including the current attempt outcome for the
    # trailing-window check (current attempt contributes a pass + its
    # misconception id, or a clean pass with None).
    improved_ids: list[str] = []
    sweep_histories = _attempt_histories(session, journey_id, norm_concept)
    sweep_pairs = [(h["passed"], h["misconception_id"]) for h in sweep_histories]
    sweep_pairs.append((passed, norm_m))
    for cand in repositories.list_counters_for_journey(session, journey_id):
        if cand.concept_id != norm_concept or not cand.active:
            continue
        if weakness_rules.has_improved(sweep_pairs, cand.misconception_id):
            repositories.set_counter_active(
                session, journey_id, norm_concept, cand.misconception_id, False
            )
            improve_reason = (
                f"improved: no recurrence in the last "
                f"{weakness_rules.IMPROVEMENT_WINDOW} relevant attempts "
                f"(all passed)"
            )
            repositories.set_recurring_flag(
                session,
                user_id,
                journey_id,
                norm_concept,
                cand.misconception_id,
                False,
                reason=improve_reason,
            )
            repositories.create_event(
                session,
                user_id,
                journey_id,
                EVENT_RECURRING_CLEARED,
                norm_concept,
                misconception_id=cand.misconception_id,
                metadata={
                    "problem_id": norm_problem,
                    "isomorphic_group_id": norm_iso,
                    "reason": improve_reason,
                },
            )
            improved_ids.append(cand.misconception_id)

    # -- append-only history ------------------------------------------------
    repositories.create_event(
        session,
        user_id,
        journey_id,
        EVENT_ATTEMPT,
        norm_concept,
        misconception_id=norm_m,
        metadata={
            "problem_id": norm_problem,
            "isomorphic_group_id": norm_iso,
            "variant_role": norm_role,
            "passed": passed,
            "success": passed,
            "execution_status": status_norm,
            "hint_used": hint_used,
            "is_transfer": resolved_transfer,
            "evidence_refs": refs,
            "attempt_number": new_attempt_count,
        },
    )
    if norm_m is not None:
        repositories.create_event(
            session,
            user_id,
            journey_id,
            EVENT_DIAGNOSIS,
            norm_concept,
            misconception_id=norm_m,
            metadata={
                "problem_id": norm_problem,
                "isomorphic_group_id": norm_iso,
                "confidence": confidence,
                "evidence_refs": refs,
                "execution_status": status_norm,
            },
        )
    now_iso = datetime.utcnow().isoformat()
    repositories.create_event(
        session,
        user_id,
        journey_id,
        EVENT_MASTERY_TRANSITION,
        norm_concept,
        misconception_id=norm_m,
        metadata={
            "problem_id": norm_problem,
            "isomorphic_group_id": norm_iso,
            "previous_mastery": previous_mastery,
            "new_mastery": new_mastery,
            "delta": delta,
            "reason": reason,
            "evidence_refs": refs,
            "execution_status": status_norm,
            "passed": passed,
            "hint_used": hint_used,
            "is_transfer": resolved_transfer,
            "band_before": band_before,
            "band_after": band_after,
            "trend": new_trend,
        },
    )
    session.flush()

    transition: dict[str, Any] = {
        "concept_id": norm_concept,
        "language_track": language_track,
        "previous_mastery": previous_mastery,
        "new_mastery": new_mastery,
        "delta": delta,
        "reason": reason,
        "evidence_refs": refs,
        "timestamp": now_iso,
        "attempt_number": new_attempt_count,
        "band_before": band_before,
        "band_after": band_after,
        "trend": new_trend,
        "passed": passed,
        "execution_status": status_norm,
        "hint_used": hint_used,
        "is_transfer": resolved_transfer,
        "problem_id": norm_problem,
        "isomorphic_group_id": norm_iso,
    }
    concept_view = get_concept_view(session, journey_id, norm_concept)
    misc_view = (
        get_misconception_view(session, journey_id, norm_concept, norm_m)
        if norm_m is not None
        else None
    )
    return {
        "transition": transition,
        "concept_view": concept_view,
        "misconception_view": misc_view,
        "is_recurring": recurring_now,
        "recurring_reason": recurring_reason,
        "improved_ids": improved_ids,
    }


# ---------------------------------------------------------------------------
# Explainability + EvidencePack bridge
# ---------------------------------------------------------------------------
def explain_mastery(
    session: Session, journey_id: int, concept_id: str
) -> dict[str, Any]:
    """Explain current mastery by tracing its append-only history.

    Returns ``{"concept_view": ..., "transitions": [...], "narrative": str}``
    where ``transitions`` are the ``mastery_transition`` events (oldest ->
    newest) with their linked attempt context, and ``narrative`` answers
    "Why is mastery X?" in one deterministic paragraph.
    """
    norm_concept = repositories.normalize_concept_id(concept_id)
    view = get_concept_view(session, journey_id, norm_concept)
    transitions = repositories.list_events_for_journey(
        session, journey_id, event_type=EVENT_MASTERY_TRANSITION,
        concept_id=norm_concept,
    )
    attempts = repositories.list_events_for_journey(
        session, journey_id, event_type=EVENT_ATTEMPT, concept_id=norm_concept
    )
    attempt_by_number = {
        (e.event_metadata or {}).get("attempt_number"): e for e in attempts
    }
    trace: list[dict[str, Any]] = []
    for event in transitions:
        meta = dict(event.event_metadata or {})
        attempt_number = meta.get("attempt_number")
        # Fallback: correlate by order when attempt_number is missing
        # (legacy rows); link nth transition to nth attempt.
        linked = attempt_by_number.get(attempt_number)
        trace.append(
            {
                "event_id": event.id,
                "created_at": _iso_or_none(event.created_at),
                "problem_id": meta.get("problem_id"),
                "previous_mastery": meta.get("previous_mastery"),
                "new_mastery": meta.get("new_mastery"),
                "delta": meta.get("delta"),
                "reason": meta.get("reason"),
                "evidence_refs": meta.get("evidence_refs", []),
                "passed": meta.get("passed"),
                "execution_status": meta.get("execution_status"),
                "misconception_id": event.misconception_id,
                "attempt_problem_id": (
                    (linked.event_metadata or {}).get("problem_id")
                    if linked is not None
                    else None
                ),
            }
        )
    recent = trace[-3:] if trace else []
    recent_bits = "; ".join(
        f"attempt on {t['problem_id']}: "
        f"{t['previous_mastery']}->{t['new_mastery']} ({t['delta']:+}) "
        f"via {t['reason']}"
        for t in recent
    )
    narrative = (
        f"Mastery for {norm_concept} ({view['language_track']}) is "
        f"{view['mastery']:.2f} ({view['band']}) after "
        f"{view['attempt_count']} attempt(s) "
        f"({view['pass_count']} passed, {view['fail_count']} failed; "
        f"trend {view['trend']}, hint dependence "
        f"{view['hint_dependence']:.2f}, transfer success "
        f"{view['transfer_success_rate']:.2f})."
    )
    if recent_bits:
        narrative += f" Recent transitions: {recent_bits}."
    else:
        narrative += " No mastery transitions recorded yet."
    if view["active_misconception_ids"]:
        narrative += (
            f" Active misconceptions: {', '.join(view['active_misconception_ids'])}."
        )
    return {"concept_view": view, "transitions": trace, "narrative": narrative}


def snapshot_for_evidence(
    session: Session,
    user_id: int,
    journey_id: int,
    concept_id: str,
    max_events: int = 10,
) -> LearnerSnapshot:
    """Build a detached ``LearnerSnapshot`` slice for the EvidencePack builder.

    Reads (never writes) the concept state, same-concept counters/flags, and
    the trailing same-concept events, converting ORM rows to plain DTOs so
    database URLs/sessions never cross into ``packages.evidence``.
    """
    norm_concept = repositories.normalize_concept_id(concept_id)
    journey = _get_journey(session, user_id, journey_id)
    state = repositories.get_concept_state(session, journey_id, norm_concept)
    concept_state = None
    if state is not None:
        concept_state = ConceptStateSnapshot(
            concept_id=norm_concept,
            stored_mastery=float(state.mastery),
            attempt_count=state.attempt_count,
            successful_attempts=state.successful_attempts,
            current_band=state.current_band,
            trend=state.trend,
            hint_count=state.hint_count,
            transfer_attempts=state.transfer_attempts,
            transfer_successes=state.transfer_successes,
        )
    counters = tuple(
        CounterSnapshot(
            concept_id=c.concept_id,
            misconception_id=c.misconception_id,
            occurrence_count=c.occurrence_count,
            active=bool(c.active),
            last_seen_at=_iso_or_none(c.last_seen_at),
        )
        for c in repositories.list_counters_for_journey(session, journey_id)
        if c.concept_id == norm_concept
    )
    flags = tuple(
        FlagSnapshot(
            concept_id=f.concept_id,
            misconception_id=f.misconception_id,
            is_recurring=bool(f.is_recurring),
            reason=f.reason,
        )
        for f in repositories.list_flags_for_journey(session, journey_id)
        if f.concept_id == norm_concept
    )
    events_all = repositories.list_events_for_journey(
        session, journey_id, concept_id=norm_concept
    )
    tail = events_all[-max_events:] if events_all else []
    events = tuple(
        EventSnapshot(
            event_type=e.event_type,
            concept_id=e.concept_id,
            misconception_id=e.misconception_id,
            created_at=_iso_or_none(e.created_at),
            metadata=dict(e.event_metadata or {}),
        )
        for e in tail
    )
    return LearnerSnapshot(
        user_id=user_id,
        journey_id=journey_id,
        language_track=journey.language_track,
        concept_state=concept_state,
        counters=counters,
        flags=flags,
        events=events,
    )


__all__ = [
    "EVENT_ATTEMPT",
    "EVENT_DIAGNOSIS",
    "EVENT_MASTERY_TRANSITION",
    "EVENT_RECURRING_CLEARED",
    "EVENT_RECURRING_DETECTED",
    "INITIAL_MASTERY",
    "ensure_concept_state",
    "explain_mastery",
    "get_concept_view",
    "get_misconception_view",
    "record_attempt",
    "snapshot_for_evidence",
]
