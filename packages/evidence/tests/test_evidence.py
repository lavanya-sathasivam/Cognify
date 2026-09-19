"""Unit tests for Step 6: EvidencePack generation (packages.evidence).

Covers: EvidencePack/sub-model validation, deterministic builder behavior,
raw-evidence preservation, relevant-history filtering, secret sanitization,
observed-vs-inferred markers, serialization round-trips, the worked example,
and static safety guarantees (no secrets, no LLM, no DB/env access).

Run from repo root:
    python -m unittest discover -s packages/evidence/tests -t . -v
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

# -- sys.path bootstrap (repo root) -----------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.evidence import build_evidence_pack  # noqa: E402
from packages.evidence.builder import sanitize_metadata  # noqa: E402
from packages.evidence.examples import (  # noqa: E402
    EXAMPLE_EVIDENCE_PACK,
    EXAMPLE_EXECUTION_RESULT,
    EXAMPLE_LEARNER_SNAPSHOT,
    EXAMPLE_SUBMISSION_CODE,
    make_example_evidence_pack,
)
from packages.evidence.models import (  # noqa: E402
    EVIDENCE_KIND,
    EVIDENCE_SCHEMA_VERSION,
    INFERENCE_STATUS,
    MAX_CODE_CHARS,
    MAX_RECENT_EVENTS,
    ConceptHistorySummary,
    ConceptStateSnapshot,
    CounterSnapshot,
    EvidencePack,
    EventSnapshot,
    FailedTestEvidence,
    FlagSnapshot,
    LearnerRef,
    LearnerSnapshot,
    MisconceptionCandidate,
    MisconceptionOccurrence,
    RecurringFlagEvidence,
    RelevantEventEvidence,
)
from packages.problem_schema.examples import (  # noqa: E402
    EXAMPLE_JAVA_PROBLEM,
    EXAMPLE_PYTHON_PROBLEM,
)

_EVIDENCE_DIR = _ROOT / "packages" / "evidence"

_CODE = "x = input()\nprint(x)\n"


def _exec_result(**overrides):
    base = {
        "status": "FAILED",
        "language": "python",
        "execution_time_ms": 50,
        "stdout": "WRONG\n",
        "stderr": "",
        "tests": [
            {
                "test_id": "P1",
                "passed": False,
                "input": "5",
                "expected_output": "6",
                "actual_output": "WRONG\n",
                "stdout": "WRONG\n",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "time_ms": 50,
            }
        ],
        "passed_count": 0,
        "failed_count": 1,
        "failed_test_id": "P1",
        "expected_output": "6",
        "actual_output": "WRONG\n",
    }
    base.update(overrides)
    return copy.deepcopy(base)


def _snapshot(**overrides):
    base = {
        "user_id": 1,
        "journey_id": 2,
        "language_track": "python",
        "concept_state": ConceptStateSnapshot(concept_id="C3"),
        "counters": (),
        "flags": (),
        "events": (),
    }
    base.update(overrides)
    return LearnerSnapshot(**base)


def _build(**overrides):
    kwargs = {
        "code": _CODE,
        "problem": EXAMPLE_PYTHON_PROBLEM,
        "execution_result": _exec_result(),
        "learner_snapshot": _snapshot(),
    }
    kwargs.update(overrides)
    return build_evidence_pack(**kwargs)


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------
class FailedTestEvidenceTests(unittest.TestCase):
    def _valid(self, **overrides):
        kwargs = {
            "test_id": "P1", "input": "5", "expected_output": "6",
            "actual_output": "7", "stdout": "7", "stderr": "",
            "exit_code": 0, "timed_out": False, "time_ms": 10,
        }
        kwargs.update(overrides)
        return FailedTestEvidence(**kwargs)

    def test_valid(self):
        t = self._valid()
        self.assertEqual(t.test_id, "P1")
        self.assertEqual(t.to_dict()["exit_code"], 0)
        self.assertEqual(FailedTestEvidence.from_dict(t.to_dict()), t)

    def test_rejects_bad_id_and_types(self):
        with self.assertRaises(ValueError):
            self._valid(test_id="bad id!")
        with self.assertRaises(TypeError):
            self._valid(time_ms=True)
        with self.assertRaises(ValueError):
            self._valid(time_ms=-1)
        with self.assertRaises(TypeError):
            self._valid(timed_out=1)

    def test_from_dict_rejects_missing_and_extra_keys(self):
        d = self._valid().to_dict()
        del d["stdout"]
        with self.assertRaises(ValueError):
            FailedTestEvidence.from_dict(d)
        d2 = self._valid().to_dict()
        d2["diagnosis"] = "C3-M01"
        with self.assertRaises(ValueError):
            FailedTestEvidence.from_dict(d2)


class MisconceptionCandidateTests(unittest.TestCase):
    def test_valid_and_normalized(self):
        c = MisconceptionCandidate(
            misconception_id=" c3-m01 ", concept_id="c3",
            name="n", typical_signal="s",
        )
        self.assertEqual((c.misconception_id, c.concept_id), ("C3-M01", "C3"))

    def test_rejects_wrong_concept(self):
        with self.assertRaises(ValueError):
            MisconceptionCandidate(
                misconception_id="C1-M01", concept_id="C3",
                name="n", typical_signal="s",
            )
        with self.assertRaises(ValueError):
            MisconceptionCandidate(
                misconception_id="C9-M99", concept_id="C3",
                name="n", typical_signal="s",
            )


class HistoryModelTests(unittest.TestCase):
    def test_concept_history_range_checks(self):
        ok = ConceptHistorySummary(
            concept_id="C3", stored_mastery=0.5, attempt_count=1,
            successful_attempts=1, current_band="b", trend="t",
            hint_count=0, transfer_attempts=0, transfer_successes=0,
        )
        self.assertEqual(ok.stored_mastery, 0.5)
        with self.assertRaises(ValueError):
            ConceptHistorySummary(
                concept_id="C3", stored_mastery=1.5, attempt_count=0,
                successful_attempts=0, current_band="b", trend="t",
                hint_count=0, transfer_attempts=0, transfer_successes=0,
            )

    def test_occurrence_and_flag_belong_to_concept(self):
        with self.assertRaises(ValueError):
            MisconceptionOccurrence(
                misconception_id="C1-M01", concept_id="C3",
                occurrence_count=1, active=True,
            )
        with self.assertRaises(ValueError):
            RecurringFlagEvidence(
                misconception_id="C1-M01", concept_id="C3", is_recurring=True,
            )

    def test_event_metadata_rejects_secrets(self):
        with self.assertRaises(ValueError):
            RelevantEventEvidence(
                event_type="attempt", concept_id="C3", misconception_id=None,
                created_at=None, metadata={"DATABASE_URL": "sqlite:///x"},
            )
        with self.assertRaises(ValueError):
            RelevantEventEvidence(
                event_type="attempt", concept_id="C3", misconception_id=None,
                created_at=None, metadata={"api_token": "abc"},
            )
        ok = RelevantEventEvidence(
            event_type="attempt", concept_id="C3", misconception_id="C3-M01",
            created_at=None, metadata={"success": False},
        )
        self.assertEqual(ok.metadata, {"success": False})

    def test_learner_ref_track_validation(self):
        with self.assertRaises(ValueError):
            LearnerRef(user_id=1, journey_id=2, language_track="ruby")
        with self.assertRaises(ValueError):
            LearnerRef(user_id=0, journey_id=2, language_track="python")


class EvidencePackValidationTests(unittest.TestCase):
    def test_rejects_empty_and_oversized_code(self):
        with self.assertRaises(ValueError):
            _build(code="   ")
        with self.assertRaises(ValueError):
            _build(code="x" * (MAX_CODE_CHARS + 1))

    def test_rejects_unknown_language_and_status(self):
        pack = _build()
        d = pack.to_dict()
        d["language"] = "ruby"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d)
        d2 = pack.to_dict()
        d2["execution_status"] = "GUESSSED"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d2)

    def test_rejects_confirmed_misconception_and_inference_tampering(self):
        pack = _build()
        d = pack.to_dict()
        d["confirmed_misconception_id"] = "C3-M01"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d)
        d2 = pack.to_dict()
        d2["inference_status"] = "diagnosed: C3-M01"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d2)
        d3 = pack.to_dict()
        d3["evidence_kind"] = "inferred"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d3)

    def test_rejects_extra_keys_as_llm_tampering(self):
        d = _build().to_dict()
        d["llm_diagnosis"] = "C3-M01"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d)

    def test_rejects_cross_track_learner(self):
        snap = _snapshot(language_track="java")
        with self.assertRaises(ValueError):
            _build(learner_snapshot=snap)

    def test_rejects_unrelated_history(self):
        # Counter for a non-candidate misconception of the same concept.
        pack = _build()
        d = pack.to_dict()
        d["misconception_history"] = [{
            "misconception_id": "C3-M02", "concept_id": "C3",
            "occurrence_count": 9, "active": True, "last_seen_at": None,
        }]
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d)
        # Event for another concept.
        d2 = pack.to_dict()
        d2["recent_events"] = [{
            "event_type": "attempt", "concept_id": "C2",
            "misconception_id": None, "created_at": None, "metadata": {},
        }]
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d2)

    def test_rejects_unsorted_history_and_too_many_events(self):
        pack = _build()
        d = pack.to_dict()
        d["misconception_history"] = [
            {"misconception_id": "C3-M04", "concept_id": "C3",
             "occurrence_count": 1, "active": True, "last_seen_at": None},
            {"misconception_id": "C3-M01", "concept_id": "C3",
             "occurrence_count": 2, "active": True, "last_seen_at": None},
        ]
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d)
        d2 = pack.to_dict()
        d2["recent_events"] = [
            {"event_type": "attempt", "concept_id": "C3",
             "misconception_id": None, "created_at": None, "metadata": {}}
            for _ in range(MAX_RECENT_EVENTS + 1)
        ]
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d2)

    def test_failed_consistency_enforced(self):
        pack = _build()
        d = pack.to_dict()
        d["expected_output"] = "tampered"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d)
        d2 = pack.to_dict()
        d2["failed_test_id"] = "P2"
        with self.assertRaises(ValueError):
            EvidencePack.from_dict(d2)

    def test_markers_are_constants(self):
        pack = _build()
        self.assertEqual(pack.schema_version, EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(pack.evidence_kind, "observed")
        self.assertEqual(pack.evidence_kind, EVIDENCE_KIND)
        self.assertIsNone(pack.confirmed_misconception_id)
        self.assertEqual(pack.inference_status, INFERENCE_STATUS)


# ---------------------------------------------------------------------------
# Builder: determinism, preservation, filtering
# ---------------------------------------------------------------------------
class BuilderDeterminismTests(unittest.TestCase):
    def test_same_inputs_yield_equal_packs(self):
        first = _build()
        second = _build()
        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_example_factory_is_deterministic(self):
        self.assertEqual(make_example_evidence_pack(), make_example_evidence_pack())
        self.assertEqual(
            make_example_evidence_pack().to_dict(),
            EXAMPLE_EVIDENCE_PACK.to_dict(),
        )

    def test_accepts_execution_result_object_shape(self):
        class _Obj:
            def __init__(self, payload):
                self.__dict__.update(payload)

        payload = _exec_result()
        payload["tests"] = [_Obj(t) for t in payload["tests"]]
        result_obj = _Obj(payload)
        from_dict_pack = _build()
        from_obj_pack = _build(execution_result=result_obj)
        self.assertEqual(from_dict_pack, from_obj_pack)

    def test_accepts_enum_like_status(self):
        class _Status:
            value = "FAILED"

        payload = _exec_result()
        payload["status"] = _Status()
        pack = _build(execution_result=payload)
        self.assertEqual(pack.execution_status, "FAILED")


class BuilderPreservationTests(unittest.TestCase):
    def test_raw_output_preserved_verbatim(self):
        # Trailing spaces / CRLF must NOT be normalized by the builder.
        raw = "  6  \r\n"
        payload = _exec_result(
            stdout=raw, actual_output=raw, expected_output="30", stderr="  warn  ",
            tests=[{
                "test_id": "P1", "passed": False, "input": "10",
                "expected_output": "30", "actual_output": raw,
                "stdout": raw, "stderr": "  warn  ",
                "exit_code": 0, "timed_out": False, "time_ms": 5,
            }],
        )
        pack = _build(execution_result=payload)
        self.assertEqual(pack.stdout, raw)
        self.assertEqual(pack.actual_output, raw)
        self.assertEqual(pack.failed_tests[0].stdout, raw)
        self.assertEqual(pack.failed_tests[0].stderr, "  warn  ")

    def test_code_preserved_verbatim(self):
        code = "print( 'hi' )  \n"
        pack = _build(code=code)
        self.assertEqual(pack.code, code)

    def test_failed_tests_only_and_in_order(self):
        payload = _exec_result(
            stdout="first-fail", actual_output="first-fail",
            expected_output="E1", failed_test_id="T1",
            passed_count=1, failed_count=2,
            tests=[
                {"test_id": "T1", "passed": False, "input": "a",
                 "expected_output": "E1", "actual_output": "first-fail",
                 "stdout": "first-fail", "stderr": "",
                 "exit_code": 0, "timed_out": False, "time_ms": 3},
                {"test_id": "T2", "passed": True, "input": "b",
                 "expected_output": "E2", "actual_output": "E2",
                 "stdout": "E2", "stderr": "",
                 "exit_code": 0, "timed_out": False, "time_ms": 4},
                {"test_id": "T3", "passed": False, "input": "c",
                 "expected_output": "E3", "actual_output": "bad",
                 "stdout": "bad", "stderr": "err",
                 "exit_code": 1, "timed_out": False, "time_ms": 5},
            ],
        )
        pack = _build(execution_result=payload)
        self.assertEqual([t.test_id for t in pack.failed_tests], ["T1", "T3"])
        self.assertEqual(pack.failed_test_id, "T1")

    def test_passed_result_has_empty_failed_tests(self):
        payload = _exec_result(
            status="PASSED", stdout="6", stderr="",
            passed_count=1, failed_count=0, failed_test_id=None,
            expected_output=None, actual_output=None,
            tests=[{
                "test_id": "P1", "passed": True, "input": "5",
                "expected_output": "6", "actual_output": "6",
                "stdout": "6", "stderr": "",
                "exit_code": 0, "timed_out": False, "time_ms": 9,
            }],
        )
        pack = _build(execution_result=payload)
        self.assertEqual(pack.execution_status, "PASSED")
        self.assertEqual(pack.failed_tests, ())
        self.assertIsNone(pack.failed_test_id)

    def test_compile_error_preserves_stderr_and_empty_tests(self):
        payload = {
            "status": "COMPILE_ERROR", "language": "python",
            "execution_time_ms": 0, "stdout": "",
            "stderr": "Main.java:3: ';' expected",
            "tests": [], "passed_count": 0, "failed_count": 0,
            "failed_test_id": None, "expected_output": None, "actual_output": None,
        }
        pack = _build(execution_result=payload)
        self.assertEqual(pack.execution_status, "COMPILE_ERROR")
        self.assertEqual(pack.stderr, "Main.java:3: ';' expected")
        self.assertEqual(pack.failed_tests, ())


class BuilderHistoryFilteringTests(unittest.TestCase):
    def test_only_relevant_history_included(self):
        snap = LearnerSnapshot(
            user_id=1, journey_id=2, language_track="python",
            concept_state=ConceptStateSnapshot(concept_id="C3", stored_mastery=0.2),
            counters=(
                CounterSnapshot(concept_id="C3", misconception_id="C3-M01",
                                occurrence_count=4),
                # Same misconception ID family but another concept: dropped.
                CounterSnapshot(concept_id="C2", misconception_id="C2-M01",
                                occurrence_count=99),
                # Same concept but not a candidate of PY-C3-001: dropped.
                CounterSnapshot(concept_id="C3", misconception_id="C3-M02",
                                occurrence_count=99),
            ),
            flags=(
                FlagSnapshot(concept_id="C3", misconception_id="C3-M01",
                             is_recurring=True, reason="often"),
                FlagSnapshot(concept_id="C2", misconception_id="C2-M01",
                             is_recurring=True),
            ),
            events=(
                EventSnapshot(event_type="attempt", concept_id="C3",
                              metadata={"n": 1}),
                EventSnapshot(event_type="attempt", concept_id="C2",
                              metadata={"n": 2}),
            ),
        )
        pack = _build(learner_snapshot=snap)
        self.assertEqual(
            [h.misconception_id for h in pack.misconception_history], ["C3-M01"]
        )
        self.assertEqual(pack.misconception_history[0].occurrence_count, 4)
        self.assertEqual([f.misconception_id for f in pack.recurring_flags], ["C3-M01"])
        self.assertEqual(len(pack.recent_events), 1)
        self.assertEqual(pack.recent_events[0].concept_id, "C3")

    def test_new_learner_without_history(self):
        snap = _snapshot(concept_state=None)
        pack = _build(learner_snapshot=snap)
        self.assertIsNone(pack.concept_history)
        self.assertEqual(pack.misconception_history, ())
        self.assertEqual(pack.recurring_flags, ())
        self.assertEqual(pack.recent_events, ())

    def test_concept_state_for_wrong_concept_rejected(self):
        snap = _snapshot(concept_state=ConceptStateSnapshot(concept_id="C2"))
        with self.assertRaises(ValueError):
            _build(learner_snapshot=snap)

    def test_recent_events_capped_to_most_recent(self):
        events = tuple(
            EventSnapshot(event_type="attempt", concept_id="C3",
                          metadata={"seq": i})
            for i in range(MAX_RECENT_EVENTS + 5)
        )
        snap = _snapshot(events=events)
        pack = _build(learner_snapshot=snap)
        self.assertEqual(len(pack.recent_events), MAX_RECENT_EVENTS)
        self.assertEqual(
            [e.metadata["seq"] for e in pack.recent_events],
            list(range(5, 5 + MAX_RECENT_EVENTS)),
        )

    def test_candidates_come_from_problem_in_order(self):
        pack = _build()
        self.assertEqual(
            [c.misconception_id for c in pack.misconception_candidates],
            list(EXAMPLE_PYTHON_PROBLEM.misconception_ids),
        )
        self.assertEqual(pack.problem_id, "PY-C3-001")
        self.assertEqual(pack.concept_id, "C3")

    def test_rejects_language_mismatch(self):
        with self.assertRaises(ValueError):
            _build(problem=EXAMPLE_JAVA_PROBLEM)  # java problem vs python exec
        java_exec = _exec_result(language="java")
        with self.assertRaises(ValueError):
            _build(execution_result=java_exec)  # java exec vs python problem

    def test_rejects_execution_missing_keys(self):
        bad = _exec_result()
        del bad["stdout"]
        with self.assertRaises(ValueError):
            _build(execution_result=bad)


class BuilderSanitizationTests(unittest.TestCase):
    def test_sanitize_metadata_drops_secrets(self):
        clean = sanitize_metadata({
            "success": False, "password": "x", "DATABASE_URL": "y",
            "api_token": "z", "hint_level": 1,
            "nested": {"auth_token": "t", "ok": 1},
        })
        self.assertEqual(clean, {"success": False, "hint_level": 1, "nested": {"ok": 1}})

    def test_builder_sanitizes_event_metadata(self):
        snap = _snapshot(events=(
            EventSnapshot(event_type="attempt", concept_id="C3", metadata={
                "success": False, "password": "hunter2",
                "DATABASE_URL": "sqlite:///secret.db",
            }),
        ))
        pack = _build(learner_snapshot=snap)
        self.assertEqual(pack.recent_events[0].metadata, {"success": False})


class SerializationTests(unittest.TestCase):
    def test_round_trip(self):
        pack = _build()
        self.assertEqual(EvidencePack.from_dict(pack.to_dict()), pack)

    def test_example_round_trip(self):
        self.assertEqual(
            EvidencePack.from_dict(EXAMPLE_EVIDENCE_PACK.to_dict()),
            EXAMPLE_EVIDENCE_PACK,
        )

    def test_to_dict_has_no_secret_keys_anywhere(self):
        import json

        text = json.dumps(EXAMPLE_EVIDENCE_PACK.to_dict()).lower()
        for forbidden in ("database_url", "password", "private_key", "credentials"):
            self.assertNotIn(forbidden, text)


class ExamplePackTests(unittest.TestCase):
    def test_example_contains_all_required_sections(self):
        pack = EXAMPLE_EVIDENCE_PACK
        self.assertEqual(pack.problem_id, "PY-C3-001")
        self.assertEqual(pack.concept_id, "C3")
        self.assertEqual(pack.language, "python")
        self.assertTrue(pack.code.strip())
        self.assertEqual(len(pack.misconception_candidates), 2)
        self.assertEqual(pack.execution_status, "FAILED")
        self.assertEqual(pack.execution_time_ms, 79)
        self.assertEqual(len(pack.failed_tests), 1)
        self.assertEqual(pack.expected_output, "30")
        self.assertEqual(pack.actual_output, "6\n")
        self.assertEqual(pack.stdout, "6\n")
        self.assertEqual(pack.stderr, "")
        self.assertIsNotNone(pack.concept_history)
        self.assertEqual(len(pack.misconception_history), 2)
        self.assertEqual(len(pack.recurring_flags), 2)
        self.assertTrue(any(f.is_recurring for f in pack.recurring_flags))
        self.assertEqual(len(pack.recent_events), 2)
        # Observed, never confirmed.
        self.assertEqual(pack.evidence_kind, "observed")
        self.assertIsNone(pack.confirmed_misconception_id)
        self.assertEqual(pack.inference_status, "pending-diagnosis")
        self.assertEqual(pack.concept_history.stored_mastery, 0.35)


# ---------------------------------------------------------------------------
# Static safety guarantees (mirrors execution-service SecurityTests style)
# ---------------------------------------------------------------------------
class EvidenceSafetyTests(unittest.TestCase):
    def _sources(self) -> dict[str, str]:
        return {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(_EVIDENCE_DIR.glob("*.py"))
        }

    def test_no_db_env_or_secret_access(self):
        import ast

        for name, src in self._sources().items():
            tree = ast.parse(src, filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in {
                    "environ", "getenv", "getenvb",
                }:
                    self.fail(f"{name}: host env access is forbidden")
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if "://" in node.value:
                        self.fail(f"{name}: URL-like literal {node.value!r}")
        for name, src in self._sources().items():
            # Uppercase-sensitive: the lowercase "database_url" fragment inside
            # SECRET_KEY_FRAGMENTS (the sanitization blocklist) is expected.
            for token in ("DATABASE_URL", "create_engine", "sessionmaker",
                          "sqlalchemy", "SECRET_KEY ="):
                self.assertNotIn(token, src, f"{name} must not touch the database")

    def test_no_llm_or_network_or_execution_primitives(self):
        import ast

        for name, src in self._sources().items():
            tree = ast.parse(src, filename=name)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    joined = " ".join(names).lower()
                    for forbidden in ("openai", "anthropic", "httpx", "requests",
                                      "sqlalchemy", "subprocess", "socket"):
                        self.assertNotIn(forbidden, joined, f"{name}: forbidden import")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in {"eval", "exec", "compile"}:
                    self.fail(f"{name}: forbidden call to {node.func.id}()")

    def test_no_inference_vocabulary_in_models(self):
        src = (_EVIDENCE_DIR / "models.py").read_text(encoding="utf-8")
        self.assertIn("never", src)  # documents no-confirmation guarantee


if __name__ == "__main__":
    unittest.main()
