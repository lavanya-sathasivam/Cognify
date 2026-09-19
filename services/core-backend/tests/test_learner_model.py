"""Unit tests for Step 4: Learner Model + SQLite database (core-backend).

Covers: database initialization, all six SQLAlchemy models, foreign keys /
relationships, unique state per (journey + concept), unique counter per
(journey + concept + misconception), and repository CRUD/read functions.

Vocabularies (concepts / languages / misconceptions) are NOT duplicated here:
tests use ``packages.taxonomy`` as the single source of truth.

Run from repo root:
    python -m unittest services.core-backend.tests.test_learner_model -v  # hyphen pkg: see note
    python -m unittest discover -s services/core-backend/tests -t . -v
    python -m unittest discover -s packages/taxonomy/tests -t . -v

NOTE: ``services/core-backend`` is not an importable package name (hyphen), so
this file bootstraps ``sys.path`` with the repo root AND the service dir, then
imports ``app.db / app.models / app.repositories`` plus ``packages.taxonomy``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# -- sys.path bootstrap (repo root + service dir) ---------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
_SERVICE_DIR = _ROOT / "services" / "core-backend"
for _p in (str(_ROOT), str(_SERVICE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app import db as db_module  # noqa: E402
from app import models, repositories  # noqa: E402
from app.db import Base, get_engine, get_session_factory, init_db  # noqa: E402
from packages.taxonomy import (  # noqa: E402
    CONCEPT_IDS,
    SUPPORTED_LANGUAGES,
    list_misconceptions,
)


def _fresh_session(testcase):
    """Create an isolated in-memory SQLite DB + open Session for one test."""
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    factory = get_session_factory(engine)
    session = factory()
    testcase.addCleanup(session.close)
    return session


class DbInitTests(unittest.TestCase):
    def test_init_creates_all_six_tables(self):
        engine = get_engine("sqlite:///:memory:")
        init_db(engine)
        self.assertEqual(
            sorted(Base.metadata.tables.keys()),
            [
                "journeys",
                "learner_concept_states",
                "learner_events",
                "misconception_counters",
                "recurring_flags",
                "users",
            ],
        )

    def test_default_url_is_sqlite(self):
        self.assertTrue(db_module.get_database_url().startswith("sqlite"))

    def test_session_scope_commits_and_closes(self):
        engine = get_engine("sqlite:///:memory:")
        init_db(engine)
        with db_module.session_scope(engine) as session:
            user = repositories.create_user(session)
            user_id = user.id
        # New scope sees the committed row.
        with db_module.session_scope(engine) as session:
            self.assertIsNotNone(repositories.get_user(session, user_id))

    def test_sqlite_enforces_foreign_keys(self):
        session = _fresh_session(self)
        # Journey pointing at a nonexistent user must violate FK.
        session.add(models.Journey(user_id=9999, language_track="python"))
        with self.assertRaises(IntegrityError):
            session.flush()
        session.rollback()


class UserTests(unittest.TestCase):
    def test_create_and_get_user(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        self.assertIsNotNone(user.id)
        self.assertEqual(repositories.get_user(session, user.id), user)

    def test_get_missing_user_returns_none(self):
        session = _fresh_session(self)
        self.assertIsNone(repositories.get_user(session, 9999))

    def test_user_ids_autoincrement(self):
        session = _fresh_session(self)
        a = repositories.create_user(session)
        b = repositories.create_user(session)
        self.assertNotEqual(a.id, b.id)


class JourneyTests(unittest.TestCase):
    def test_create_python_and_java_tracks(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        py = repositories.create_journey(session, user.id, "python")
        java = repositories.create_journey(session, user.id, "java")
        self.assertEqual(py.language_track, "python")
        self.assertEqual(java.language_track, "java")
        self.assertTrue(py.active and java.active)

    def test_language_track_normalized(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "  Python ")
        self.assertEqual(journey.language_track, "python")

    def test_supported_languages_match_taxonomy(self):
        self.assertEqual(tuple(SUPPORTED_LANGUAGES), ("python", "java"))

    def test_unknown_language_rejected(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        for bad in ["c++", "rust", "", "  "]:
            with self.assertRaises(ValueError, msg=bad):
                repositories.create_journey(session, user.id, bad)

    def test_unknown_user_rejected(self):
        session = _fresh_session(self)
        with self.assertRaises(ValueError):
            repositories.create_journey(session, 9999, "python")

    def test_get_and_list_journeys(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        py = repositories.create_journey(session, user.id, "python")
        java = repositories.create_journey(session, user.id, "java")
        self.assertEqual(repositories.get_journey(session, py.id).id, py.id)
        self.assertIsNone(repositories.get_journey(session, 9999))
        listed = repositories.list_journeys_for_user(session, user.id)
        self.assertEqual([j.id for j in listed], [py.id, java.id])

    def test_new_active_journey_deactivates_previous_same_track(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        first = repositories.create_journey(session, user.id, "python")
        second = repositories.create_journey(session, user.id, "python")
        self.assertFalse(repositories.get_journey(session, first.id).active)
        self.assertTrue(repositories.get_journey(session, second.id).active)
        # Other track untouched.
        other = repositories.create_journey(session, user.id, "java")
        self.assertTrue(repositories.get_journey(session, other.id).active)

    def test_get_active_journey(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        self.assertIsNone(repositories.get_active_journey(session, user.id, "python"))
        journey = repositories.create_journey(session, user.id, "python")
        active = repositories.get_active_journey(session, user.id, "PYTHON")
        self.assertEqual(active.id, journey.id)

    def test_set_journey_active_reactivates_and_switches(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        first = repositories.create_journey(session, user.id, "python")
        second = repositories.create_journey(session, user.id, "python")
        repositories.set_journey_active(session, first.id, True)
        self.assertTrue(repositories.get_journey(session, first.id).active)
        self.assertFalse(repositories.get_journey(session, second.id).active)

    def test_relationships_user_journeys(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "python")
        session.refresh(user)
        self.assertEqual([j.id for j in user.journeys], [journey.id])
        self.assertEqual(journey.user.id, user.id)


class ConceptStateTests(unittest.TestCase):
    def _user_journey(self, session, track="python"):
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, track)
        return user, journey

    def test_get_or_create_normalizes_concept(self):
        session = _fresh_session(self)
        user, journey = self._user_journey(session)
        state, created = repositories.get_or_create_concept_state(
            session, user.id, journey.id, "c1"
        )
        self.assertTrue(created)
        self.assertEqual(state.concept_id, "C1")
        self.assertEqual(state.mastery, 0.0)

    def test_unique_state_per_journey_and_concept(self):
        session = _fresh_session(self)
        user, journey = self._user_journey(session)
        first, created_first = repositories.get_or_create_concept_state(
            session, user.id, journey.id, "C1"
        )
        second, created_second = repositories.get_or_create_concept_state(
            session, user.id, journey.id, "C1"
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.id, second.id)
        # Raw duplicate insert violates the DB unique constraint.
        session.add(
            models.LearnerConceptState(
                user_id=user.id, journey_id=journey.id, concept_id="C1"
            )
        )
        with self.assertRaises(IntegrityError):
            session.flush()
        session.rollback()

    def test_same_concept_independent_across_journeys(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        py = repositories.create_journey(session, user.id, "python")
        java = repositories.create_journey(session, user.id, "java")
        py_state, _ = repositories.get_or_create_concept_state(
            session, user.id, py.id, "C1"
        )
        java_state, _ = repositories.get_or_create_concept_state(
            session, user.id, java.id, "C1"
        )
        self.assertNotEqual(py_state.id, java_state.id)

    def test_all_taxonomy_concepts_accepted(self):
        session = _fresh_session(self)
        user, journey = self._user_journey(session)
        self.assertEqual(len(CONCEPT_IDS), 8)
        for cid in CONCEPT_IDS:
            state, created = repositories.get_or_create_concept_state(
                session, user.id, journey.id, cid
            )
            self.assertTrue(created, cid)
            self.assertEqual(state.concept_id, cid)

    def test_unknown_concept_rejected(self):
        session = _fresh_session(self)
        user, journey = self._user_journey(session)
        for bad in ["C0", "C9", "CX", "", "  "]:
            with self.assertRaises(ValueError, msg=bad):
                repositories.get_or_create_concept_state(
                    session, user.id, journey.id, bad
                )

    def test_journey_of_other_user_rejected(self):
        session = _fresh_session(self)
        user_a = repositories.create_user(session)
        user_b = repositories.create_user(session)
        journey_a = repositories.create_journey(session, user_a.id, "python")
        with self.assertRaises(ValueError):
            repositories.get_or_create_concept_state(
                session, user_b.id, journey_a.id, "C1"
            )

    def test_get_and_list_states(self):
        session = _fresh_session(self)
        user, journey = self._user_journey(session)
        self.assertIsNone(repositories.get_concept_state(session, journey.id, "C1"))
        repositories.get_or_create_concept_state(session, user.id, journey.id, "C2")
        repositories.get_or_create_concept_state(session, user.id, journey.id, "C1")
        self.assertEqual(
            repositories.get_concept_state(session, journey.id, "c1").concept_id, "C1"
        )
        listed = repositories.list_concept_states_for_journey(session, journey.id)
        self.assertEqual([s.concept_id for s in listed], ["C1", "C2"])

    def test_update_state_stores_values_no_formula(self):
        session = _fresh_session(self)
        user, journey = self._user_journey(session)
        repositories.get_or_create_concept_state(session, user.id, journey.id, "C1")
        updated = repositories.update_concept_state(
            session,
            journey.id,
            "C1",
            mastery=0.75,
            attempt_count=4,
            successful_attempts=3,
            current_band="developing",
            trend="improving",
            hint_count=1,
            transfer_attempts=2,
            transfer_successes=1,
        )
        self.assertEqual(updated.mastery, 0.75)
        self.assertEqual(updated.attempt_count, 4)
        self.assertEqual(updated.current_band, "developing")
        self.assertEqual(updated.trend, "improving")

    def test_update_validates_ranges_and_fields(self):
        session = _fresh_session(self)
        user, journey = self._user_journey(session)
        repositories.get_or_create_concept_state(session, user.id, journey.id, "C1")
        with self.assertRaises(ValueError):  # mastery out of range
            repositories.update_concept_state(session, journey.id, "C1", mastery=1.5)
        with self.assertRaises(ValueError):  # negative count
            repositories.update_concept_state(session, journey.id, "C1", attempt_count=-1)
        with self.assertRaises(ValueError):  # unknown field
            repositories.update_concept_state(session, journey.id, "C1", nope=1)
        with self.assertRaises(ValueError):  # missing row
            repositories.update_concept_state(session, journey.id, "C2", mastery=0.5)

    def test_check_constraint_concept_id_uses_taxonomy(self):
        checks = " ".join(
            str(c.sqltext)
            for c in models.LearnerConceptState.__table__.constraints
            if hasattr(c, "sqltext")
        )
        for cid in CONCEPT_IDS:
            self.assertIn(cid, checks, f"CHECK constraint should mention {cid}")


class MisconceptionCounterTests(unittest.TestCase):
    def _setup(self, session, concept="C1", misconception="C1-M01"):
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "python")
        return user, journey

    def test_get_or_create_and_increment(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        counter, created = repositories.get_or_create_counter(
            session, user.id, journey.id, "C1", "c1-m01"
        )
        self.assertTrue(created)
        self.assertEqual(counter.misconception_id, "C1-M01")
        self.assertEqual(counter.occurrence_count, 0)
        counter = repositories.increment_counter(
            session, user.id, journey.id, "C1", "C1-M01"
        )
        self.assertEqual(counter.occurrence_count, 1)
        counter = repositories.increment_counter(
            session, user.id, journey.id, "C1", "C1-M01", increment=2
        )
        self.assertEqual(counter.occurrence_count, 3)
        self.assertIsNotNone(counter.last_seen_at)

    def test_unique_counter_per_journey_concept_misconception(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        first, created_first = repositories.get_or_create_counter(
            session, user.id, journey.id, "C1", "C1-M01"
        )
        second, created_second = repositories.get_or_create_counter(
            session, user.id, journey.id, "C1", "C1-M01"
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.id, second.id)
        session.add(
            models.MisconceptionCounter(
                user_id=user.id,
                journey_id=journey.id,
                concept_id="C1",
                misconception_id="C1-M01",
            )
        )
        with self.assertRaises(IntegrityError):
            session.flush()
        session.rollback()

    def test_different_misconceptions_are_independent(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        c1, _ = repositories.get_or_create_counter(
            session, user.id, journey.id, "C1", "C1-M01"
        )
        c2, created = repositories.get_or_create_counter(
            session, user.id, journey.id, "C1", "C1-M02"
        )
        self.assertTrue(created)
        self.assertNotEqual(c1.id, c2.id)

    def test_misconception_must_belong_to_concept(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        # C1-M01 belongs to C1, not C2.
        with self.assertRaises(ValueError):
            repositories.get_or_create_counter(
                session, user.id, journey.id, "C2", "C1-M01"
            )
        with self.assertRaises(ValueError):
            repositories.increment_counter(
                session, user.id, journey.id, "C2", "C1-M01"
            )

    def test_unknown_misconception_rejected(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        with self.assertRaises(ValueError):
            repositories.get_or_create_counter(
                session, user.id, journey.id, "C1", "C1-M99"
            )

    def test_every_taxonomy_concept_has_usable_misconception(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        for cid in CONCEPT_IDS:
            mid = list_misconceptions(cid)[0].id
            counter, created = repositories.get_or_create_counter(
                session, user.id, journey.id, cid, mid
            )
            self.assertTrue(created, f"{cid}/{mid}")
            self.assertEqual(counter.concept_id, cid)

    def test_get_list_and_active_toggle(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        self.assertIsNone(
            repositories.get_counter(session, journey.id, "C1", "C1-M01")
        )
        repositories.increment_counter(session, user.id, journey.id, "C1", "C1-M01")
        repositories.get_or_create_counter(session, user.id, journey.id, "C1", "C1-M02")
        listed = repositories.list_counters_for_journey(session, journey.id)
        self.assertEqual(
            [(c.concept_id, c.misconception_id) for c in listed],
            [("C1", "C1-M01"), ("C1", "C1-M02")],
        )
        off = repositories.set_counter_active(
            session, journey.id, "C1", "C1-M01", False
        )
        self.assertFalse(off.active)
        on = repositories.set_counter_active(session, journey.id, "C1", "C1-M01", True)
        self.assertTrue(on.active)

    def test_increment_must_be_positive_int(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        for bad in [0, -1, 1.5, True, "2"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                repositories.increment_counter(
                    session, user.id, journey.id, "C1", "C1-M01", increment=bad
                )


class RecurringFlagTests(unittest.TestCase):
    def test_set_get_update_flag(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "python")
        self.assertIsNone(repositories.get_flag(session, journey.id, "C1", "C1-M01"))
        flag = repositories.set_recurring_flag(
            session, user.id, journey.id, "C1", "C1-M01", True, reason="3+ occurrences"
        )
        self.assertTrue(flag.is_recurring)
        self.assertEqual(flag.reason, "3+ occurrences")
        fetched = repositories.get_flag(session, journey.id, "c1", "c1-m01")
        self.assertEqual(fetched.id, flag.id)
        cleared = repositories.set_recurring_flag(
            session, user.id, journey.id, "C1", "C1-M01", False
        )
        self.assertFalse(cleared.is_recurring)
        self.assertEqual(cleared.id, flag.id)  # upsert, not duplicate

    def test_unique_flag_per_journey_concept_misconception(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "python")
        first = repositories.set_recurring_flag(
            session, user.id, journey.id, "C1", "C1-M01", True
        )
        second = repositories.set_recurring_flag(
            session, user.id, journey.id, "C1", "C1-M01", False
        )
        self.assertEqual(first.id, second.id)

    def test_flag_misconception_must_belong_to_concept(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "python")
        with self.assertRaises(ValueError):
            repositories.set_recurring_flag(
                session, user.id, journey.id, "C2", "C1-M01", True
            )

    def test_list_flags_with_recurring_only_filter(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "python")
        repositories.set_recurring_flag(
            session, user.id, journey.id, "C1", "C1-M01", True
        )
        repositories.set_recurring_flag(
            session, user.id, journey.id, "C1", "C1-M02", False
        )
        all_flags = repositories.list_flags_for_journey(session, journey.id)
        self.assertEqual(len(all_flags), 2)
        recurring = repositories.list_flags_for_journey(
            session, journey.id, recurring_only=True
        )
        self.assertEqual(len(recurring), 1)
        self.assertEqual(recurring[0].misconception_id, "C1-M01")


class LearnerEventTests(unittest.TestCase):
    def _setup(self, session):
        user = repositories.create_user(session)
        journey = repositories.create_journey(session, user.id, "python")
        return user, journey

    def test_create_and_get_event(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        event = repositories.create_event(
            session,
            user.id,
            journey.id,
            "attempt",
            "C1",
            misconception_id="C1-M01",
            metadata={"success": False},
        )
        self.assertEqual(event.event_type, "attempt")
        self.assertEqual(event.concept_id, "C1")
        self.assertEqual(event.misconception_id, "C1-M01")
        self.assertEqual(event.event_metadata, {"success": False})
        self.assertEqual(repositories.get_event(session, event.id).id, event.id)

    def test_metadata_defaults_to_empty_dict(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        event = repositories.create_event(session, user.id, journey.id, "hint", "C2")
        self.assertEqual(event.event_metadata, {})
        self.assertIsNone(event.misconception_id)

    def test_events_are_append_only_and_ordered(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        first = repositories.create_event(session, user.id, journey.id, "attempt", "C1")
        second = repositories.create_event(session, user.id, journey.id, "hint", "C1")
        listed = repositories.list_events_for_journey(session, journey.id)
        self.assertEqual([e.id for e in listed], [first.id, second.id])

    def test_list_events_filters_and_limit(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        repositories.create_event(session, user.id, journey.id, "attempt", "C1")
        repositories.create_event(session, user.id, journey.id, "hint", "C1")
        repositories.create_event(session, user.id, journey.id, "attempt", "C2")
        self.assertEqual(
            len(
                repositories.list_events_for_journey(
                    session, journey.id, event_type="attempt"
                )
            ),
            2,
        )
        self.assertEqual(
            len(
                repositories.list_events_for_journey(
                    session, journey.id, concept_id="c1"
                )
            ),
            2,
        )
        limited = repositories.list_events_for_journey(session, journey.id, limit=2)
        self.assertEqual(len(limited), 2)
        with self.assertRaises(ValueError):
            repositories.list_events_for_journey(session, journey.id, limit=0)

    def test_event_validation(self):
        session = _fresh_session(self)
        user, journey = self._setup(session)
        with self.assertRaises(ValueError):  # empty type
            repositories.create_event(session, user.id, journey.id, "  ", "C1")
        with self.assertRaises(ValueError):  # unknown concept
            repositories.create_event(session, user.id, journey.id, "attempt", "C9")
        with self.assertRaises(ValueError):  # misconception of another concept
            repositories.create_event(
                session, user.id, journey.id, "attempt", "C2",
                misconception_id="C1-M01",
            )
        other_user = repositories.create_user(session)
        with self.assertRaises(ValueError):  # journey belongs to someone else
            repositories.create_event(
                session, other_user.id, journey.id, "attempt", "C1"
            )


class TrackIsolationTests(unittest.TestCase):
    def test_python_and_java_state_fully_separate(self):
        session = _fresh_session(self)
        user = repositories.create_user(session)
        py = repositories.create_journey(session, user.id, "python")
        java = repositories.create_journey(session, user.id, "java")
        py_state, _ = repositories.get_or_create_concept_state(
            session, user.id, py.id, "C3"
        )
        java_state, _ = repositories.get_or_create_concept_state(
            session, user.id, java.id, "C3"
        )
        repositories.update_concept_state(session, py.id, "C3", mastery=0.9)
        self.assertEqual(
            repositories.get_concept_state(session, py.id, "C3").mastery, 0.9
        )
        self.assertEqual(
            repositories.get_concept_state(session, java.id, "C3").mastery, 0.0
        )
        self.assertNotEqual(py_state.id, java_state.id)

    def test_two_users_do_not_share_state(self):
        session = _fresh_session(self)
        user_a = repositories.create_user(session)
        user_b = repositories.create_user(session)
        journey_a = repositories.create_journey(session, user_a.id, "python")
        journey_b = repositories.create_journey(session, user_b.id, "python")
        state_a, _ = repositories.get_or_create_concept_state(
            session, user_a.id, journey_a.id, "C1"
        )
        state_b, _ = repositories.get_or_create_concept_state(
            session, user_b.id, journey_b.id, "C1"
        )
        self.assertNotEqual(state_a.id, state_b.id)


class TaxonomyReuseTests(unittest.TestCase):
    def test_no_duplicated_concept_list(self):
        import inspect

        from app import models as models_module

        source = inspect.getsource(models_module)
        # Models must reference the taxonomy (single source of truth) rather
        # than hard-coding the C1..C8 / python+java vocabularies.
        self.assertIn("CONCEPT_IDS", source)
        self.assertIn("SUPPORTED_LANGUAGES", source)

    def test_repository_validation_uses_taxonomy(self):
        import inspect

        from app import repositories as repos_module

        source = inspect.getsource(repos_module)
        self.assertIn("packages.taxonomy", source)
        self.assertIn("misconception_belongs_to", source)


if __name__ == "__main__":
    unittest.main()
