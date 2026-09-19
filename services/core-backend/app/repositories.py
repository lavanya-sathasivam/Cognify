"""COGNIFY core-backend — repository functions (basic CRUD/reads only).

Rules enforced here (Python side, using ``packages.taxonomy`` as the single
source of truth — no duplicated concept/language lists):
- ``language_track`` normalized to lower-case and must be in SUPPORTED_LANGUAGES.
- ``concept_id`` normalized to UPPER-case and must be a known taxonomy concept.
- ``misconception_id`` normalized to UPPER-case, must be known AND must belong
  to the given ``concept_id`` (misconception_belongs_to).
- Every child row verifies its journey belongs to the given user, which keeps
  the python/java tracks separated (state is always scoped via journey_id).

Mastery is never calculated here; ``update_concept_state`` only stores the
values it is given. Functions ``flush`` (surfacing IntegrityErrors early) but
never commit — the caller (session_scope / tests) owns the transaction.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.taxonomy import (
    SUPPORTED_LANGUAGES,
    is_valid_concept,
    is_valid_misconception,
    misconception_belongs_to,
)

from .models import (
    Journey,
    LearnerConceptState,
    LearnerEvent,
    MisconceptionCounter,
    RecurringFlag,
    User,
)


# ---------------------------------------------------------------------------
# Validation helpers (single source: packages.taxonomy)
# ---------------------------------------------------------------------------
def normalize_language_track(language_track: str) -> str:
    if not isinstance(language_track, str):
        raise TypeError(
            f"language_track must be str, got {type(language_track).__name__}."
        )
    norm = language_track.strip().lower()
    if norm not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unknown language_track {language_track!r}. "
            f"Use one of {list(SUPPORTED_LANGUAGES)}."
        )
    return norm


def normalize_concept_id(concept_id: str) -> str:
    if not isinstance(concept_id, str):
        raise TypeError(f"concept_id must be str, got {type(concept_id).__name__}.")
    norm = concept_id.strip().upper()
    if not norm or not is_valid_concept(norm):
        raise ValueError(f"Unknown concept_id {concept_id!r}.")
    return norm


def normalize_misconception_id(misconception_id: str) -> str:
    if not isinstance(misconception_id, str):
        raise TypeError(
            f"misconception_id must be str, got {type(misconception_id).__name__}."
        )
    norm = misconception_id.strip().upper()
    if not norm or not is_valid_misconception(norm):
        raise ValueError(f"Unknown misconception_id {misconception_id!r}.")
    return norm


def _require_misconception_for_concept(misconception_id: str, concept_id: str) -> str:
    norm_m = normalize_misconception_id(misconception_id)
    if not misconception_belongs_to(norm_m, concept_id):
        raise ValueError(
            f"Misconception {norm_m!r} does not belong to concept {concept_id!r}."
        )
    return norm_m


def _get_journey_or_raise(session: Session, journey_id: int) -> Journey:
    journey = session.get(Journey, journey_id)
    if journey is None:
        raise ValueError(f"Unknown journey_id {journey_id!r}.")
    return journey


def _assert_journey_of_user(journey: Journey, user_id: int) -> None:
    if journey.user_id != user_id:
        raise ValueError(
            f"Journey {journey.id!r} belongs to user {journey.user_id!r}, "
            f"not user {user_id!r} (tracks must not cross)."
        )


def _require_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}.")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value!r}.")
    return value


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def create_user(session: Session) -> User:
    user = User()
    session.add(user)
    session.flush()
    return user


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


# ---------------------------------------------------------------------------
# Journeys (language-track separation lives here)
# ---------------------------------------------------------------------------
def create_journey(
    session: Session, user_id: int, language_track: str, active: bool = True
) -> Journey:
    if get_user(session, user_id) is None:
        raise ValueError(f"Unknown user_id {user_id!r}.")
    if not isinstance(active, bool):
        raise TypeError(f"active must be bool, got {type(active).__name__}.")
    norm_lang = normalize_language_track(language_track)
    if active:
        for existing in session.scalars(
            select(Journey).where(
                Journey.user_id == user_id,
                Journey.language_track == norm_lang,
                Journey.active.is_(True),
            )
        ):
            existing.active = False
    journey = Journey(user_id=user_id, language_track=norm_lang, active=active)
    session.add(journey)
    session.flush()
    return journey


def get_journey(session: Session, journey_id: int) -> Journey | None:
    return session.get(Journey, journey_id)


def list_journeys_for_user(session: Session, user_id: int) -> list[Journey]:
    return list(
        session.scalars(
            select(Journey).where(Journey.user_id == user_id).order_by(Journey.id)
        )
    )


def get_active_journey(
    session: Session, user_id: int, language_track: str
) -> Journey | None:
    norm_lang = normalize_language_track(language_track)
    return session.scalar(
        select(Journey)
        .where(
            Journey.user_id == user_id,
            Journey.language_track == norm_lang,
            Journey.active.is_(True),
        )
        .order_by(Journey.id.desc())
    )


def set_journey_active(
    session: Session, journey_id: int, active: bool
) -> Journey:
    if not isinstance(active, bool):
        raise TypeError(f"active must be bool, got {type(active).__name__}.")
    journey = _get_journey_or_raise(session, journey_id)
    if active:
        for other in session.scalars(
            select(Journey).where(
                Journey.user_id == journey.user_id,
                Journey.language_track == journey.language_track,
                Journey.active.is_(True),
                Journey.id != journey.id,
            )
        ):
            other.active = False
    journey.active = active
    session.flush()
    return journey


# ---------------------------------------------------------------------------
# LearnerConceptState (unique per journey + concept; store only, no formula)
# ---------------------------------------------------------------------------
_CONCEPT_STATE_MUTABLE = {
    "mastery",
    "attempt_count",
    "successful_attempts",
    "current_band",
    "trend",
    "hint_count",
    "transfer_attempts",
    "transfer_successes",
}


def get_or_create_concept_state(
    session: Session, user_id: int, journey_id: int, concept_id: str
) -> tuple[LearnerConceptState, bool]:
    norm_concept = normalize_concept_id(concept_id)
    journey = _get_journey_or_raise(session, journey_id)
    _assert_journey_of_user(journey, user_id)
    existing = session.scalar(
        select(LearnerConceptState).where(
            LearnerConceptState.journey_id == journey_id,
            LearnerConceptState.concept_id == norm_concept,
        )
    )
    if existing is not None:
        if existing.user_id != user_id:
            raise ValueError("Concept state user mismatch (tracks must not cross).")
        return existing, False
    state = LearnerConceptState(
        user_id=user_id, journey_id=journey_id, concept_id=norm_concept
    )
    session.add(state)
    session.flush()
    return state, True


def get_concept_state(
    session: Session, journey_id: int, concept_id: str
) -> LearnerConceptState | None:
    norm_concept = normalize_concept_id(concept_id)
    return session.scalar(
        select(LearnerConceptState).where(
            LearnerConceptState.journey_id == journey_id,
            LearnerConceptState.concept_id == norm_concept,
        )
    )


def list_concept_states_for_journey(
    session: Session, journey_id: int
) -> list[LearnerConceptState]:
    _get_journey_or_raise(session, journey_id)
    return list(
        session.scalars(
            select(LearnerConceptState)
            .where(LearnerConceptState.journey_id == journey_id)
            .order_by(LearnerConceptState.concept_id)
        )
    )


def update_concept_state(
    session: Session, journey_id: int, concept_id: str, **fields
) -> LearnerConceptState:
    state = get_concept_state(session, journey_id, concept_id)
    if state is None:
        raise ValueError(
            f"No concept state for journey {journey_id!r}, concept {concept_id!r}."
        )
    unknown = set(fields) - _CONCEPT_STATE_MUTABLE
    if unknown:
        raise ValueError(f"Unknown concept-state fields: {sorted(unknown)}.")
    if "mastery" in fields:
        value = fields["mastery"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(f"mastery must be a number, got {type(value).__name__}.")
        if not 0 <= float(value) <= 1:
            raise ValueError(f"mastery must be in [0, 1], got {value!r}.")
        state.mastery = float(value)
    for int_field in (
        "attempt_count",
        "successful_attempts",
        "hint_count",
        "transfer_attempts",
        "transfer_successes",
    ):
        if int_field in fields:
            setattr(state, int_field, _require_non_negative_int(fields[int_field], int_field))
    for str_field in ("current_band", "trend"):
        if str_field in fields:
            value = fields[str_field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{str_field} must be a non-empty string.")
            setattr(state, str_field, value.strip())
    session.flush()
    return state


# ---------------------------------------------------------------------------
# MisconceptionCounter (unique per journey + concept + misconception)
# ---------------------------------------------------------------------------
def get_or_create_counter(
    session: Session,
    user_id: int,
    journey_id: int,
    concept_id: str,
    misconception_id: str,
) -> tuple[MisconceptionCounter, bool]:
    norm_concept = normalize_concept_id(concept_id)
    norm_m = _require_misconception_for_concept(misconception_id, norm_concept)
    journey = _get_journey_or_raise(session, journey_id)
    _assert_journey_of_user(journey, user_id)
    existing = session.scalar(
        select(MisconceptionCounter).where(
            MisconceptionCounter.journey_id == journey_id,
            MisconceptionCounter.concept_id == norm_concept,
            MisconceptionCounter.misconception_id == norm_m,
        )
    )
    if existing is not None:
        if existing.user_id != user_id:
            raise ValueError("Counter user mismatch (tracks must not cross).")
        return existing, False
    counter = MisconceptionCounter(
        user_id=user_id,
        journey_id=journey_id,
        concept_id=norm_concept,
        misconception_id=norm_m,
    )
    session.add(counter)
    session.flush()
    return counter, True


def get_counter(
    session: Session, journey_id: int, concept_id: str, misconception_id: str
) -> MisconceptionCounter | None:
    norm_concept = normalize_concept_id(concept_id)
    norm_m = normalize_misconception_id(misconception_id)
    return session.scalar(
        select(MisconceptionCounter).where(
            MisconceptionCounter.journey_id == journey_id,
            MisconceptionCounter.concept_id == norm_concept,
            MisconceptionCounter.misconception_id == norm_m,
        )
    )


def list_counters_for_journey(
    session: Session, journey_id: int
) -> list[MisconceptionCounter]:
    _get_journey_or_raise(session, journey_id)
    return list(
        session.scalars(
            select(MisconceptionCounter)
            .where(MisconceptionCounter.journey_id == journey_id)
            .order_by(
                MisconceptionCounter.concept_id, MisconceptionCounter.misconception_id
            )
        )
    )


def increment_counter(
    session: Session,
    user_id: int,
    journey_id: int,
    concept_id: str,
    misconception_id: str,
    increment: int = 1,
) -> MisconceptionCounter:
    if type(increment) is not int or increment <= 0:
        raise ValueError(f"increment must be a positive int, got {increment!r}.")
    counter, _ = get_or_create_counter(
        session, user_id, journey_id, concept_id, misconception_id
    )
    counter.occurrence_count += increment
    counter.last_seen_at = datetime.utcnow()
    session.flush()
    return counter


def set_counter_active(
    session: Session,
    journey_id: int,
    concept_id: str,
    misconception_id: str,
    active: bool,
) -> MisconceptionCounter:
    if not isinstance(active, bool):
        raise TypeError(f"active must be bool, got {type(active).__name__}.")
    counter = get_counter(session, journey_id, concept_id, misconception_id)
    if counter is None:
        raise ValueError("No such misconception counter.")
    counter.active = active
    session.flush()
    return counter


# ---------------------------------------------------------------------------
# RecurringFlag
# ---------------------------------------------------------------------------
def set_recurring_flag(
    session: Session,
    user_id: int,
    journey_id: int,
    concept_id: str,
    misconception_id: str,
    is_recurring: bool,
    reason: str | None = None,
) -> RecurringFlag:
    norm_concept = normalize_concept_id(concept_id)
    norm_m = _require_misconception_for_concept(misconception_id, norm_concept)
    if not isinstance(is_recurring, bool):
        raise TypeError(f"is_recurring must be bool, got {type(is_recurring).__name__}.")
    if reason is not None and not isinstance(reason, str):
        raise TypeError(f"reason must be str or None, got {type(reason).__name__}.")
    journey = _get_journey_or_raise(session, journey_id)
    _assert_journey_of_user(journey, user_id)
    existing = session.scalar(
        select(RecurringFlag).where(
            RecurringFlag.journey_id == journey_id,
            RecurringFlag.concept_id == norm_concept,
            RecurringFlag.misconception_id == norm_m,
        )
    )
    if existing is None:
        flag = RecurringFlag(
            user_id=user_id,
            journey_id=journey_id,
            concept_id=norm_concept,
            misconception_id=norm_m,
            is_recurring=is_recurring,
            reason=reason,
        )
        session.add(flag)
        session.flush()
        return flag
    if existing.user_id != user_id:
        raise ValueError("Flag user mismatch (tracks must not cross).")
    existing.is_recurring = is_recurring
    existing.reason = reason
    if is_recurring:
        existing.detected_at = datetime.utcnow()
    session.flush()
    return existing


def get_flag(
    session: Session, journey_id: int, concept_id: str, misconception_id: str
) -> RecurringFlag | None:
    norm_concept = normalize_concept_id(concept_id)
    norm_m = normalize_misconception_id(misconception_id)
    return session.scalar(
        select(RecurringFlag).where(
            RecurringFlag.journey_id == journey_id,
            RecurringFlag.concept_id == norm_concept,
            RecurringFlag.misconception_id == norm_m,
        )
    )


def list_flags_for_journey(
    session: Session, journey_id: int, recurring_only: bool = False
) -> list[RecurringFlag]:
    _get_journey_or_raise(session, journey_id)
    stmt = select(RecurringFlag).where(RecurringFlag.journey_id == journey_id)
    if recurring_only:
        stmt = stmt.where(RecurringFlag.is_recurring.is_(True))
    return list(
        session.scalars(stmt.order_by(RecurringFlag.concept_id, RecurringFlag.misconception_id))
    )


# ---------------------------------------------------------------------------
# LearnerEvent (append-only)
# ---------------------------------------------------------------------------
def create_event(
    session: Session,
    user_id: int,
    journey_id: int,
    event_type: str,
    concept_id: str,
    misconception_id: str | None = None,
    metadata: dict | None = None,
) -> LearnerEvent:
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type must be a non-empty string.")
    norm_concept = normalize_concept_id(concept_id)
    norm_m = None
    if misconception_id is not None:
        norm_m = _require_misconception_for_concept(misconception_id, norm_concept)
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise TypeError(f"metadata must be a dict, got {type(metadata).__name__}.")
    journey = _get_journey_or_raise(session, journey_id)
    _assert_journey_of_user(journey, user_id)
    event = LearnerEvent(
        user_id=user_id,
        journey_id=journey_id,
        event_type=event_type.strip(),
        concept_id=norm_concept,
        misconception_id=norm_m,
        event_metadata=dict(metadata),
    )
    session.add(event)
    session.flush()
    return event


def get_event(session: Session, event_id: int) -> LearnerEvent | None:
    return session.get(LearnerEvent, event_id)


def list_events_for_journey(
    session: Session,
    journey_id: int,
    event_type: str | None = None,
    concept_id: str | None = None,
    limit: int | None = None,
) -> list[LearnerEvent]:
    _get_journey_or_raise(session, journey_id)
    stmt = select(LearnerEvent).where(LearnerEvent.journey_id == journey_id)
    if event_type is not None:
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type filter must be a non-empty string.")
        stmt = stmt.where(LearnerEvent.event_type == event_type.strip())
    if concept_id is not None:
        stmt = stmt.where(LearnerEvent.concept_id == normalize_concept_id(concept_id))
    stmt = stmt.order_by(LearnerEvent.id)
    if limit is not None:
        if type(limit) is not int or limit <= 0:
            raise ValueError(f"limit must be a positive int, got {limit!r}.")
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


__all__ = [
    "create_event",
    "create_journey",
    "create_user",
    "get_active_journey",
    "get_concept_state",
    "get_counter",
    "get_event",
    "get_flag",
    "get_journey",
    "get_or_create_concept_state",
    "get_or_create_counter",
    "get_user",
    "increment_counter",
    "list_concept_states_for_journey",
    "list_counters_for_journey",
    "list_events_for_journey",
    "list_flags_for_journey",
    "list_journeys_for_user",
    "normalize_concept_id",
    "normalize_language_track",
    "normalize_misconception_id",
    "set_counter_active",
    "set_journey_active",
    "set_recurring_flag",
    "update_concept_state",
]
