"""COGNIFY evidence — deterministic EvidencePack builder (Step 6).

Converts (code + Problem + ExecutionResult + LearnerSnapshot) into an
EvidencePack for the future AI diagnosis service.

Determinism contract:
- Pure function of its inputs: same inputs always yield an equal pack.
- No clock, no randomness, no UUIDs, no I/O, no environment reads.
- Raw execution strings are copied verbatim (no output normalization).
- Candidate order follows the problem; history lists use canonical sorted
  order; recent events keep input order and take the trailing slice.

Safety contract:
- Accepts detached snapshots only — never a DB session, engine, or URL.
- Includes only relevant history: same-concept state, candidate-ID counters
  and flags, same-concept recent events capped at ``max_recent_events``.
- Sanitizes event metadata (drops secret-like keys); output validation
  rejects any surviving secret-like key.
- Never confirms a misconception: candidates stay candidates; the pack's
  ``confirmed_misconception_id`` is always None.

This module is stdlib-only. It duck-types the execution result (dict or an
object with the ExecutionResult attributes, e.g. the pydantic model from
services/execution-service) so this package never imports service code.
"""
from __future__ import annotations

from typing import Any

from packages.problem_schema.models import Problem
from packages.taxonomy import get_misconception

from .models import (
    EVIDENCE_KIND,
    EVIDENCE_SCHEMA_VERSION,
    INFERENCE_STATUS,
    MAX_CODE_CHARS,
    MAX_RECENT_EVENTS,
    SECRET_KEY_FRAGMENTS,
    ConceptHistorySummary,
    EvidencePack,
    FailedTestEvidence,
    LearnerRef,
    LearnerSnapshot,
    MisconceptionCandidate,
    MisconceptionOccurrence,
    RecurringFlagEvidence,
    RelevantEventEvidence,
    normalize_execution_status,
    normalize_language,
)


def _is_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower().replace("-", "_").replace(" ", "_")
    return any(frag in lowered for frag in SECRET_KEY_FRAGMENTS)


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``metadata`` minus secret-like keys (deterministic).

    Nested dict values are sanitized recursively; other values are kept by
    reference-free shallow copy semantics (new containers, same scalars).
    Key order of surviving entries is preserved.
    """
    if not isinstance(metadata, dict):
        raise TypeError(f"metadata must be a dict, got {type(metadata).__name__}.")
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if _is_secret_key(key):
            continue
        if isinstance(value, dict):
            value = sanitize_metadata(value)
        elif isinstance(value, list):
            value = [
                sanitize_metadata(item) if isinstance(item, dict) else item
                for item in value
            ]
        clean[key] = value
    return clean


def _exec_field(result: Any, name: str) -> Any:
    """Read one execution-result field from a dict or attribute object."""
    if isinstance(result, dict):
        if name not in result:
            raise ValueError(f"ExecutionResult dict missing key: {name!r}.")
        return result[name]
    value = getattr(result, name, None)
    # Distinguish "missing attribute" from "present but None".
    if value is None and not hasattr(result, name):
        raise ValueError(f"ExecutionResult object missing attribute: {name!r}.")
    return value


def _exec_status_str(result: Any) -> str:
    raw = _exec_field(result, "status")
    # Accept the execution-service Enum (has .value) or a plain string.
    if not isinstance(raw, str):
        raw = getattr(raw, "value", raw)
    if not isinstance(raw, str):
        raise TypeError(
            f"ExecutionResult status must be str, got {type(raw).__name__}."
        )
    return normalize_execution_status(raw)


def _exec_tests(result: Any) -> list[Any]:
    tests = _exec_field(result, "tests")
    if tests is None:
        return []
    if not isinstance(tests, (list, tuple)):
        raise TypeError(
            f"ExecutionResult tests must be a list, got {type(tests).__name__}."
        )
    return list(tests)


def _test_field(test: Any, name: str) -> Any:
    if isinstance(test, dict):
        if name not in test:
            raise ValueError(f"TestCaseResult dict missing key: {name!r}.")
        return test[name]
    if not hasattr(test, name):
        raise ValueError(f"TestCaseResult object missing attribute: {name!r}.")
    return getattr(test, name)


def build_evidence_pack(
    *,
    code: str,
    problem: Problem,
    execution_result: Any,
    learner_snapshot: LearnerSnapshot,
    max_recent_events: int = MAX_RECENT_EVENTS,
) -> EvidencePack:
    """Build a deterministic EvidencePack from observed inputs.

    Args:
        code: Verbatim student submission (never altered, only validated).
        problem: The attempted ``packages.problem_schema.Problem``.
        execution_result: ExecutionResult dict (``to_dict()``) or the
            execution-service result object; raw strings copied verbatim.
        learner_snapshot: Detached ``LearnerSnapshot`` (plain data only).
        max_recent_events: Cap for same-concept recent events
            (positive int, defaults to MAX_RECENT_EVENTS).

    Raises:
        TypeError / ValueError: on any invalid, mismatched, or cross-track
            input. Language must agree across problem, execution, and
            learner track; history must belong to the problem's concept.
    """
    if not isinstance(code, str) or not code.strip():
        raise (
            TypeError(f"code must be str, got {type(code).__name__}.")
            if not isinstance(code, str)
            else ValueError("code must be a non-empty string.")
        )
    if len(code) > MAX_CODE_CHARS:
        raise ValueError(f"code exceeds {MAX_CODE_CHARS} characters.")
    if not isinstance(problem, Problem):
        raise TypeError(
            f"problem must be packages.problem_schema.Problem, "
            f"got {type(problem).__name__}."
        )
    if not isinstance(learner_snapshot, LearnerSnapshot):
        raise TypeError(
            "learner_snapshot must be LearnerSnapshot, "
            f"got {type(learner_snapshot).__name__}."
        )
    if type(max_recent_events) is not int or max_recent_events < 1:
        raise ValueError(
            f"max_recent_events must be a positive int, got {max_recent_events!r}."
        )
    if max_recent_events > MAX_RECENT_EVENTS:
        raise ValueError(
            f"max_recent_events={max_recent_events} exceeds the pack maximum "
            f"{MAX_RECENT_EVENTS}; evidence must stay minimal."
        )

    # -- language agreement (track separation) -----------------------------
    problem_lang = normalize_language(problem.language)
    exec_lang_raw = _exec_field(execution_result, "language")
    if not isinstance(exec_lang_raw, str):
        raise TypeError(
            "ExecutionResult language must be str, "
            f"got {type(exec_lang_raw).__name__}."
        )
    exec_lang = normalize_language(exec_lang_raw)
    if exec_lang != problem_lang:
        raise ValueError(
            f"Execution language {exec_lang!r} does not match problem "
            f"language {problem_lang!r}."
        )
    if learner_snapshot.language_track != problem_lang:
        raise ValueError(
            f"Learner track {learner_snapshot.language_track!r} does not match "
            f"problem language {problem_lang!r} (tracks must not cross)."
        )

    concept_id = problem.concept_id  # already normalized UPPER by Problem.
    candidate_ids = tuple(problem.misconception_ids)  # problem order preserved.

    # -- candidates (enriched deterministically from the taxonomy) -----------
    candidates = tuple(
        MisconceptionCandidate(
            misconception_id=mid,
            concept_id=concept_id,
            name=get_misconception(mid).name,
            typical_signal=get_misconception(mid).typical_signal,
        )
        for mid in candidate_ids
    )
    candidate_set = set(candidate_ids)

    # -- execution (raw copy; no normalization) ------------------------------
    status = _exec_status_str(execution_result)
    execution_time_ms = _exec_field(execution_result, "execution_time_ms")
    if type(execution_time_ms) is not int:
        raise TypeError(
            "ExecutionResult execution_time_ms must be int, "
            f"got {type(execution_time_ms).__name__}."
        )
    if execution_time_ms < 0:
        raise ValueError("ExecutionResult execution_time_ms must be >= 0.")
    stdout = _exec_field(execution_result, "stdout")
    stderr = _exec_field(execution_result, "stderr")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise TypeError("ExecutionResult stdout/stderr must be str.")
    passed_count = _exec_field(execution_result, "passed_count")
    failed_count = _exec_field(execution_result, "failed_count")
    for label, value in (("passed_count", passed_count), ("failed_count", failed_count)):
        if type(value) is not int or value < 0:
            raise (
                TypeError(f"ExecutionResult {label} must be int, got {type(value).__name__}.")
                if type(value) is not int
                else ValueError(f"ExecutionResult {label} must be >= 0.")
            )
    failed_test_id = _exec_field(execution_result, "failed_test_id")
    expected_output = _exec_field(execution_result, "expected_output")
    actual_output = _exec_field(execution_result, "actual_output")
    for label, value in (
        ("failed_test_id", failed_test_id),
        ("expected_output", expected_output),
        ("actual_output", actual_output),
    ):
        if value is not None and not isinstance(value, str):
            raise TypeError(f"ExecutionResult {label} must be str or None.")

    raw_tests = _exec_tests(execution_result)
    failed_tests_list: list[FailedTestEvidence] = []
    for entry in raw_tests:
        passed = _test_field(entry, "passed")
        if not isinstance(passed, bool):
            raise TypeError("TestCaseResult passed must be bool.")
        if passed:
            continue
        failed_tests_list.append(
            FailedTestEvidence(
                test_id=_test_field(entry, "test_id"),
                input=_test_field(entry, "input"),
                expected_output=_test_field(entry, "expected_output"),
                actual_output=_test_field(entry, "actual_output"),
                stdout=_test_field(entry, "stdout"),
                stderr=_test_field(entry, "stderr"),
                exit_code=_test_field(entry, "exit_code"),
                timed_out=_test_field(entry, "timed_out"),
                time_ms=_test_field(entry, "time_ms"),
            )
        )

    # -- learner history (relevant slice only) -------------------------------
    learner = LearnerRef(
        user_id=learner_snapshot.user_id,
        journey_id=learner_snapshot.journey_id,
        language_track=learner_snapshot.language_track,
    )

    concept_history: ConceptHistorySummary | None = None
    state = learner_snapshot.concept_state
    if state is not None:
        if state.concept_id != concept_id:
            raise ValueError(
                f"concept_state is for {state.concept_id!r}, not attempted concept "
                f"{concept_id!r}; pass only the relevant slice."
            )
        concept_history = ConceptHistorySummary(
            concept_id=state.concept_id,
            stored_mastery=state.stored_mastery,
            attempt_count=state.attempt_count,
            successful_attempts=state.successful_attempts,
            current_band=state.current_band,
            trend=state.trend,
            hint_count=state.hint_count,
            transfer_attempts=state.transfer_attempts,
            transfer_successes=state.transfer_successes,
        )

    misconception_history = tuple(
        sorted(
            (
                MisconceptionOccurrence(
                    misconception_id=c.misconception_id,
                    concept_id=c.concept_id,
                    occurrence_count=c.occurrence_count,
                    active=c.active,
                    last_seen_at=c.last_seen_at,
                )
                for c in learner_snapshot.counters
                if c.concept_id == concept_id and c.misconception_id in candidate_set
            ),
            key=lambda h: h.misconception_id,
        )
    )
    recurring_flags = tuple(
        sorted(
            (
                RecurringFlagEvidence(
                    misconception_id=f.misconception_id,
                    concept_id=f.concept_id,
                    is_recurring=f.is_recurring,
                    reason=f.reason,
                )
                for f in learner_snapshot.flags
                if f.concept_id == concept_id and f.misconception_id in candidate_set
            ),
            key=lambda f: f.misconception_id,
        )
    )
    relevant_events = [
        e for e in learner_snapshot.events if e.concept_id == concept_id
    ]
    recent_slice = relevant_events[-max_recent_events:] if relevant_events else []
    recent_events = tuple(
        RelevantEventEvidence(
            event_type=e.event_type,
            concept_id=e.concept_id,
            misconception_id=e.misconception_id,
            created_at=e.created_at,
            metadata=sanitize_metadata(dict(e.metadata or {})),
        )
        for e in recent_slice
    )

    return EvidencePack(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        code=code,
        language=problem_lang,
        problem_id=problem.problem_id,
        concept_id=concept_id,
        misconception_candidates=candidates,
        execution_status=status,
        execution_time_ms=execution_time_ms,
        stdout=stdout,
        stderr=stderr,
        passed_count=passed_count,
        failed_count=failed_count,
        failed_test_id=failed_test_id,
        expected_output=expected_output,
        actual_output=actual_output,
        failed_tests=tuple(failed_tests_list),
        learner=learner,
        concept_history=concept_history,
        misconception_history=misconception_history,
        recurring_flags=recurring_flags,
        recent_events=recent_events,
        evidence_kind=EVIDENCE_KIND,
        confirmed_misconception_id=None,
        inference_status=INFERENCE_STATUS,
    )


__all__ = ["build_evidence_pack", "sanitize_metadata"]
