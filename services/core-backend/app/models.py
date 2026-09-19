"""COGNIFY core-backend — learner-model tables (store only, no calculations).

Mastery is STORED here, never calculated (a later step owns the formula).
Concept / language vocabularies are NOT duplicated: CHECK constraints are
generated from ``packages.taxonomy`` (CONCEPT_IDS / SUPPORTED_LANGUAGES),
which ``packages.problem_schema`` also uses, so all three stay consistent.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.taxonomy import CONCEPT_IDS, SUPPORTED_LANGUAGES

from .db import Base

_LANGUAGE_IN = ", ".join(f"'{lang}'" for lang in SUPPORTED_LANGUAGES)
_CONCEPT_IN = ", ".join(f"'{cid}'" for cid in CONCEPT_IDS)


class User(Base):
    """A Cognify learner (auth lives elsewhere; this is just an identity row)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    journeys: Mapped[list["Journey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    concept_states: Mapped[list["LearnerConceptState"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    misconception_counters: Mapped[list["MisconceptionCounter"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recurring_flags: Mapped[list["RecurringFlag"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    events: Mapped[list["LearnerEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"User(id={self.id!r})"


class Journey(Base):
    """One language-track learning journey; state is namespaced per journey.

    Language-track separation: ``language_track`` is CHECK-constrained to the
    taxonomy's SUPPORTED_LANGUAGES, and every learner-state row points at a
    journey (repositories additionally verify ``journey.user_id == user_id``).
    """

    __tablename__ = "journeys"
    __table_args__ = (
        CheckConstraint(
            f"language_track IN ({_LANGUAGE_IN})", name="ck_journeys_language_track"
        ),
        Index("ix_journeys_user_track", "user_id", "language_track"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    language_track: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="journeys")
    concept_states: Mapped[list["LearnerConceptState"]] = relationship(
        back_populates="journey", cascade="all, delete-orphan"
    )
    misconception_counters: Mapped[list["MisconceptionCounter"]] = relationship(
        back_populates="journey", cascade="all, delete-orphan"
    )
    recurring_flags: Mapped[list["RecurringFlag"]] = relationship(
        back_populates="journey", cascade="all, delete-orphan"
    )
    events: Mapped[list["LearnerEvent"]] = relationship(
        back_populates="journey", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"Journey(id={self.id!r}, user_id={self.user_id!r}, "
            f"language_track={self.language_track!r}, active={self.active!r})"
        )


class LearnerConceptState(Base):
    """Per-(journey, concept) mastery/state snapshot (values stored, not computed)."""

    __tablename__ = "learner_concept_states"
    __table_args__ = (
        UniqueConstraint("journey_id", "concept_id", name="uq_state_journey_concept"),
        CheckConstraint(f"concept_id IN ({_CONCEPT_IN})", name="ck_state_concept_id"),
        CheckConstraint("mastery >= 0 AND mastery <= 1", name="ck_state_mastery_range"),
        CheckConstraint("attempt_count >= 0", name="ck_state_attempt_count"),
        CheckConstraint("successful_attempts >= 0", name="ck_state_success_count"),
        CheckConstraint("hint_count >= 0", name="ck_state_hint_count"),
        CheckConstraint("transfer_attempts >= 0", name="ck_state_transfer_attempts"),
        CheckConstraint("transfer_successes >= 0", name="ck_state_transfer_successes"),
        Index("ix_states_journey", "journey_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    journey_id: Mapped[int] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(String(8), nullable=False)

    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_band: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unassessed"
    )
    trend: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transfer_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transfer_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="concept_states")
    journey: Mapped["Journey"] = relationship(back_populates="concept_states")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"LearnerConceptState(journey_id={self.journey_id!r}, "
            f"concept_id={self.concept_id!r}, mastery={self.mastery!r})"
        )


class MisconceptionCounter(Base):
    """Per-(journey, concept, misconception) occurrence counter."""

    __tablename__ = "misconception_counters"
    __table_args__ = (
        UniqueConstraint(
            "journey_id",
            "concept_id",
            "misconception_id",
            name="uq_counter_journey_concept_misconception",
        ),
        CheckConstraint(f"concept_id IN ({_CONCEPT_IN})", name="ck_counter_concept_id"),
        CheckConstraint("occurrence_count >= 0", name="ck_counter_occurrence_count"),
        Index("ix_counters_journey", "journey_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    journey_id: Mapped[int] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(String(8), nullable=False)
    misconception_id: Mapped[str] = mapped_column(String(16), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="misconception_counters")
    journey: Mapped["Journey"] = relationship(back_populates="misconception_counters")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"MisconceptionCounter(journey_id={self.journey_id!r}, "
            f"misconception_id={self.misconception_id!r}, "
            f"occurrence_count={self.occurrence_count!r})"
        )


class RecurringFlag(Base):
    """Whether a misconception is currently flagged as recurring."""

    __tablename__ = "recurring_flags"
    __table_args__ = (
        UniqueConstraint(
            "journey_id",
            "concept_id",
            "misconception_id",
            name="uq_flag_journey_concept_misconception",
        ),
        CheckConstraint(f"concept_id IN ({_CONCEPT_IN})", name="ck_flag_concept_id"),
        Index("ix_flags_journey", "journey_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    journey_id: Mapped[int] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(String(8), nullable=False)
    misconception_id: Mapped[str] = mapped_column(String(16), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="recurring_flags")
    journey: Mapped["Journey"] = relationship(back_populates="recurring_flags")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"RecurringFlag(journey_id={self.journey_id!r}, "
            f"misconception_id={self.misconception_id!r}, "
            f"is_recurring={self.is_recurring!r})"
        )


class LearnerEvent(Base):
    """Append-only learning event log (metadata stored as JSON, never executed)."""

    __tablename__ = "learner_events"
    __table_args__ = (
        CheckConstraint(f"concept_id IN ({_CONCEPT_IN})", name="ck_event_concept_id"),
        Index("ix_events_journey", "journey_id"),
        Index("ix_events_journey_type", "journey_id", "event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    journey_id: Mapped[int] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    concept_id: Mapped[str] = mapped_column(String(8), nullable=False)
    misconception_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Attribute is `event_metadata` (column name stays `metadata`); `metadata`
    # alone would clash with DeclarativeBase.metadata.
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="events")
    journey: Mapped["Journey"] = relationship(back_populates="events")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"LearnerEvent(id={self.id!r}, journey_id={self.journey_id!r}, "
            f"event_type={self.event_type!r}, concept_id={self.concept_id!r})"
        )


__all__ = [
    "Journey",
    "LearnerConceptState",
    "LearnerEvent",
    "MisconceptionCounter",
    "RecurringFlag",
    "User",
]
