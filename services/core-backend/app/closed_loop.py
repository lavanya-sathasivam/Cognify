"""COGNIFY core-backend — closed-loop learner integration (Step 11).

Orchestrates the existing deterministic components into one closed learning
flow::

    VerificationResult (Step 10, pure)
      -> record_attempt() (Step 8 learner engine, owns mastery + history)
      -> get_concept_view / get_misconception_view (Step 8 read APIs)
      -> recommend_next_actions() (Step 9 adaptive engine, owns ranking)
      -> ClosedLoopResult

OWNERSHIP (this module coordinates; it duplicates nothing):

- Execution owns code execution / test results / terminal statuses.
- Diagnosis owns misconception identification / confidence / grounding.
- Verification (Step 10) owns whether the intervention produced verified
  improvement. Its verdict is consumed here, never recomputed.
- Learner Model (Step 8) owns persistent mastery state, misconception
  history, recurring-weakness detection, trend, transfer evidence, and all
  mastery updates. Every mutation below goes through the existing
  ``learner_engine.record_attempt`` contract; the mastery formula
  (``packages.mastery``) is never copied here.
- Adaptive Engine (Step 9) owns next-action recommendation and roadmap
  ranking. Recommendations come only from the existing
  ``recommend_next_actions`` API; no policy rule lives here.

VERIFICATION -> LEARNER MAPPING (deterministic, pure ``plan_records``):

- VERIFIED_IMPROVED: record the original retry as a clean ``canonical``
  pass AND the transfer as a ``transfer`` pass (``is_transfer=True``).
  Passes are recorded *clean* (no ``diagnosed_misconception_id``) so Step
  8's own improvement sweep can resolve the weakness; the target
  misconception context is preserved in ``evidence_refs`` instead (see
  below). Transfer evidence lands in ``transfer_attempts`` /
  ``transfer_successes``, never as an unrelated concept attempt.
- SURFACE_FIX: record the original retry as a clean ``canonical`` pass
  and the transfer as a ``transfer`` failure with the target
  misconception attached. The unresolved weakness is therefore preserved
  (counter + recurring evaluation run on the failure) and the concept is
  never marked mastered merely because the original passed — mastery is
  whatever Step 8's formula produces from the pass-plus-fail pair.
- NOT_IMPROVED: record only the failed original retry (``canonical``)
  with the target misconception attached. The transfer result, if any,
  is intentionally NOT recorded: verification verdicts ignore transfer
  when the original retry failed, and recording it would double-penalize
  mastery for evidence the verdict discarded.
- INCOMPLETE: zero mutations, zero manufactured attempts, zero
  recommendations. Reason: "Verification evidence is incomplete; learner
  state was not mutated."

MISCONCEPTION-CONTEXT RULE (why passes are clean): Step 8's
``has_improved`` resolves a misconception only when the trailing window
holds passes that do NOT re-contain the target id. Attaching the target
id to a passing record would increment its counter and block resolution
forever. Failed records therefore carry ``diagnosed_misconception_id``;
passing records carry ``verification-target:<ID>`` inside
``evidence_refs`` so the intervention context stays auditable in the
attempt/transition event metadata without corrupting counter semantics.

ISOMORPHIC GROUP: ``record_attempt`` requires a non-empty group. The
verification group is used when present; otherwise a deterministic
fallback ``CLOSED-LOOP-<CONCEPT>-<original-problem-id>`` is synthesized
(shared by both records of the loop so R3 grouping still links them).
The fallback is bookkeeping only and is documented in the evidence refs.

LANGUAGE ISOLATION: ``(user_id, journey_id, language_track, concept_id)``
must agree across context, journey row, and verification result. A Python
learner state is never updated from a Java attempt and vice versa.

IDEMPOTENCY LIMITATION: Step 8's event log is append-only with
autoincrement ids and no natural deduplication key, so re-running the
same closed loop records the attempts again. Step 11 documents this
instead of inventing a database-level solution (no new tables, no new
ORM, no direct SQL, no new persistence layer).

PERSISTENCE: follows the existing repository/event architecture
(``repositories`` flush; the caller owns commit/rollback, exactly like
``record_attempt`` callers). No LLM calls, no frontend state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from packages.adaptive import (
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    ProblemInfo,
    Recommendation,
    explain_recommendations,
    recommend_next_actions,
)
from packages.verification import (
    ExecutionOutcome,
    VerificationOutcome,
    VerificationResult,
)

from . import learner_engine, repositories
from .models import Journey

INCOMPLETE_REASON: str = (
    "Verification evidence is incomplete; learner state was not mutated."
)

# Step 10 (verification) and Step 8 (learner engine) spell the two
# terminal pass/fail statuses differently. This explicit table bridges the
# vocabularies with no invented meaning: a verification PASS is exactly the
# execution-service PASSED status Step 8 validates via
# ``mastery_formula.severity_for_status``. The three error statuses are
# spelled identically on both sides.
EXECUTION_STATUS_FOR_OUTCOME: dict[str, str] = {
    "PASS": "PASSED",
    "FAIL": "FAILED",
    "COMPILE_ERROR": "COMPILE_ERROR",
    "RUNTIME_ERROR": "RUNTIME_ERROR",
    "TIMEOUT": "TIMEOUT",
}

ORIGINAL_KIND: str = "original_retry"
TRANSFER_KIND: str = "transfer"

ORIGINAL_VARIANT_ROLE: str = "canonical"
TRANSFER_VARIANT_ROLE: str = "transfer"


# ---------------------------------------------------------------------------
# Small validators (input shapes only; domain vocabularies delegate to the
# existing taxonomy-backed normalizers so nothing is duplicated)
# ---------------------------------------------------------------------------
def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}.")
    if value <= 0:
        raise ValueError(f"{field_name} must be a positive int, got {value!r}.")
    return value


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


def _validate_extra_refs(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            "extra_evidence_refs must be a list/tuple of str, "
            f"got {type(value).__name__}."
        )
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("extra_evidence_refs entries must be non-empty strings.")
        refs.append(item.strip())
    if len(set(refs)) != len(refs):
        raise ValueError(f"extra_evidence_refs contains duplicates: {refs!r}.")
    return tuple(refs)


def _coerce_problems(value: object) -> tuple[ProblemInfo, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"problems must be a list/tuple of ProblemInfo, got {type(value).__name__}."
        )
    items = tuple(value)
    coerced: list[ProblemInfo] = []
    for item in items:
        if isinstance(item, ProblemInfo):
            coerced.append(item)
        elif isinstance(item, dict):
            coerced.append(ProblemInfo.from_dict(item))
        else:
            raise TypeError(
                "problems entries must be ProblemInfo or dict, "
                f"got {type(item).__name__}."
            )
    return tuple(coerced)


def _coerce_curriculum(value: object) -> CurriculumInfo | None:
    if value is None:
        return None
    if isinstance(value, CurriculumInfo):
        return value
    if isinstance(value, dict):
        return CurriculumInfo.from_dict(value)
    raise TypeError(
        f"curriculum must be CurriculumInfo, dict, or None, got {type(value).__name__}."
    )


# ---------------------------------------------------------------------------
# ClosedLoopContext (pure input)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClosedLoopContext:
    """Everything the closed loop needs (pure input, no side effects).

    - ``user_id`` / ``journey_id`` scope the Step 8 mutation; the journey
      row is the source of truth for ``language_track``.
    - ``language_track`` / ``concept_id`` / ``problem_id`` /
      ``transfer_problem_id`` must agree with the journey row AND the
      verification result (contradictions are rejected, never reconciled).
    - ``verification_result`` is the Step 10 verdict (consumed as-is).
    - ``hint_used`` / ``diagnostic_confidence`` / ``extra_evidence_refs``
      are attempt metadata forwarded to ``record_attempt``.
    - ``problems`` / ``curriculum`` are catalog metadata for the Step 9
      call (each problem must belong to ``concept_id``; curriculum
      defaults to the taxonomy prerequisites when omitted).
    """

    user_id: int
    journey_id: int
    language_track: str
    concept_id: str
    problem_id: str
    verification_result: VerificationResult
    transfer_problem_id: str | None = None
    hint_used: bool = False
    diagnostic_confidence: float | None = None
    extra_evidence_refs: tuple[str, ...] | list[str] | None = ()
    problems: tuple[ProblemInfo, ...] | list[ProblemInfo | dict[str, Any]] | None = ()
    curriculum: CurriculumInfo | dict[str, Any] | None = None

    def __post_init__(self) -> None:
        user_id = _require_positive_int(self.user_id, "user_id")
        journey_id = _require_positive_int(self.journey_id, "journey_id")
        norm_track = repositories.normalize_language_track(self.language_track)
        norm_concept = repositories.normalize_concept_id(self.concept_id)
        norm_problem = _require_non_empty_str(self.problem_id, "problem_id")
        norm_transfer_pid: str | None = None
        if self.transfer_problem_id is not None:
            norm_transfer_pid = _require_non_empty_str(
                self.transfer_problem_id, "transfer_problem_id"
            )
            if norm_transfer_pid == norm_problem:
                raise ValueError(
                    "transfer_problem_id must differ from problem_id."
                )
        if not isinstance(self.verification_result, VerificationResult):
            raise TypeError(
                "verification_result must be VerificationResult, "
                f"got {type(self.verification_result).__name__}."
            )
        result = self.verification_result
        if result.concept_id != norm_concept:
            raise ValueError(
                f"verification concept {result.concept_id!r} does not match "
                f"context concept {norm_concept!r}."
            )
        if result.language_track != norm_track:
            raise ValueError(
                f"verification track {result.language_track!r} does not match "
                f"context track {norm_track!r} (tracks must not cross)."
            )
        if result.original_problem_id != norm_problem:
            raise ValueError(
                f"verification original {result.original_problem_id!r} does not "
                f"match context problem_id {norm_problem!r}."
            )
        if result.transfer_problem_id != norm_transfer_pid:
            raise ValueError(
                f"verification transfer {result.transfer_problem_id!r} does not "
                f"match context transfer_problem_id {norm_transfer_pid!r}."
            )
        hint_used = _require_bool(self.hint_used, "hint_used")
        confidence = _validate_confidence(self.diagnostic_confidence)
        extra_refs = _validate_extra_refs(self.extra_evidence_refs)
        problems = _coerce_problems(self.problems)
        for problem in problems:
            if problem.concept_id != norm_concept:
                raise ValueError(
                    f"Problem {problem.problem_id!r} is for concept "
                    f"{problem.concept_id!r}, not context concept "
                    f"{norm_concept!r} (contradictory problem metadata)."
                )
        curriculum = _coerce_curriculum(self.curriculum)
        if curriculum is not None and curriculum.concept_id != norm_concept:
            raise ValueError(
                f"Curriculum is for concept {curriculum.concept_id!r}, not "
                f"context concept {norm_concept!r}."
            )

        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "journey_id", journey_id)
        object.__setattr__(self, "language_track", norm_track)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "problem_id", norm_problem)
        object.__setattr__(self, "transfer_problem_id", norm_transfer_pid)
        object.__setattr__(self, "hint_used", hint_used)
        object.__setattr__(self, "diagnostic_confidence", confidence)
        object.__setattr__(self, "extra_evidence_refs", extra_refs)
        object.__setattr__(self, "problems", problems)
        object.__setattr__(self, "curriculum", curriculum)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping (verification nested)."""
        return {
            "user_id": self.user_id,
            "journey_id": self.journey_id,
            "language_track": self.language_track,
            "concept_id": self.concept_id,
            "problem_id": self.problem_id,
            "transfer_problem_id": self.transfer_problem_id,
            "verification_result": self.verification_result.to_dict(),
            "hint_used": self.hint_used,
            "diagnostic_confidence": self.diagnostic_confidence,
            "extra_evidence_refs": list(self.extra_evidence_refs or ()),
            "problems": [p.to_dict() for p in (self.problems or ())],
            "curriculum": self.curriculum.to_dict() if self.curriculum else None,
        }


# ---------------------------------------------------------------------------
# AttemptPlan (pure planned record_attempt call)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AttemptPlan:
    """One planned ``record_attempt`` call (pure, DB-free)."""

    kind: str  # ORIGINAL_KIND ("original_retry") or TRANSFER_KIND ("transfer")
    problem_id: str
    variant_role: str
    is_transfer: bool
    passed: bool
    execution_status: str
    diagnosed_misconception_id: str | None
    diagnostic_confidence: float | None
    hint_used: bool
    isomorphic_group_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in (ORIGINAL_KIND, TRANSFER_KIND):
            raise ValueError(
                f"kind must be {ORIGINAL_KIND!r} or {TRANSFER_KIND!r}, "
                f"got {self.kind!r}."
            )
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "problem_id": self.problem_id,
            "variant_role": self.variant_role,
            "is_transfer": self.is_transfer,
            "passed": self.passed,
            "execution_status": self.execution_status,
            "diagnosed_misconception_id": self.diagnosed_misconception_id,
            "diagnostic_confidence": self.diagnostic_confidence,
            "hint_used": self.hint_used,
            "isomorphic_group_id": self.isomorphic_group_id,
            "evidence_refs": list(self.evidence_refs),
        }


def _require_outcome_str(
    outcome: ExecutionOutcome | str | None, *, what: str
) -> str:
    """Map a Step 10 outcome to the Step 8 execution-status vocabulary.

    ``PASS`` -> ``PASSED``, ``FAIL`` -> ``FAILED`` (explicit
    ``EXECUTION_STATUS_FOR_OUTCOME`` table); error statuses pass through
    unchanged. A missing outcome raises instead of inventing one.
    """
    if outcome is None:
        raise ValueError(
            f"Step 11 API gap: verification verdict requires a {what} outcome "
            "but the VerificationResult carries none; refusing to invent one."
        )
    raw = outcome.value if isinstance(outcome, ExecutionOutcome) else str(outcome).strip().upper()
    if not raw:
        raise ValueError(
            f"Step 11 API gap: empty {what} outcome; refusing to invent one."
        )
    try:
        return EXECUTION_STATUS_FOR_OUTCOME[raw]
    except KeyError:
        raise ValueError(
            f"Step 11 API gap: {what} outcome {raw!r} has no Step 8 "
            f"execution-status mapping (known: {sorted(EXECUTION_STATUS_FOR_OUTCOME)})."
        ) from None


def _base_evidence_refs(
    context: ClosedLoopContext,
) -> tuple[str, ...]:
    """Shared deterministic evidence refs for every planned attempt."""
    result = context.verification_result
    assert isinstance(result.reason_code, object)
    refs = [
        f"verification-outcome:{result.outcome.value}",
        f"verification-reason:{result.reason_code.value}",
        f"verification-target:{result.target_misconception_id or 'NONE'}",
    ]
    refs.extend(context.extra_evidence_refs or ())
    # Deterministic de-duplication (preserve first-seen order).
    seen: set[str] = set()
    unique: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique.append(ref)
    return tuple(unique)


def _iso_group_for(context: ClosedLoopContext) -> str:
    group = context.verification_result.isomorphic_group_id
    if group is not None:
        return group
    return f"CLOSED-LOOP-{context.concept_id}-{context.problem_id}"


def plan_records(context: ClosedLoopContext) -> tuple[AttemptPlan, ...]:
    """Plan the ``record_attempt`` calls for ``context`` (pure, DB-free).

    Returns ``()`` for INCOMPLETE (no mutation, nothing manufactured).
    Raises ``TypeError`` for non-context input. Never touches Step 8/9.
    """
    if not isinstance(context, ClosedLoopContext):
        raise TypeError(
            f"context must be ClosedLoopContext, got {type(context).__name__}."
        )
    result = context.verification_result
    outcome = result.outcome
    if outcome is VerificationOutcome.INCOMPLETE:
        return ()

    base_refs = _base_evidence_refs(context)
    group = _iso_group_for(context)
    target = result.target_misconception_id

    def _refs(kind: str, problem_id: str, status: str) -> tuple[str, ...]:
        return (*base_refs, f"verification-{kind}:{problem_id}:{status}")

    if outcome is VerificationOutcome.VERIFIED_IMPROVED:
        original_status = _require_outcome_str(
            result.original_outcome, what="original-retry"
        )
        transfer_status = _require_outcome_str(
            result.transfer_outcome, what="transfer"
        )
        transfer_pid = context.transfer_problem_id
        assert transfer_pid is not None  # Step 10 guarantees it for PASS+PASS
        return (
            AttemptPlan(
                kind=ORIGINAL_KIND,
                problem_id=context.problem_id,
                variant_role=ORIGINAL_VARIANT_ROLE,
                is_transfer=False,
                passed=True,
                execution_status=original_status,
                diagnosed_misconception_id=None,
                diagnostic_confidence=None,
                hint_used=context.hint_used,
                isomorphic_group_id=group,
                evidence_refs=_refs(ORIGINAL_KIND, context.problem_id, original_status),
            ),
            AttemptPlan(
                kind=TRANSFER_KIND,
                problem_id=transfer_pid,
                variant_role=TRANSFER_VARIANT_ROLE,
                is_transfer=True,
                passed=True,
                execution_status=transfer_status,
                diagnosed_misconception_id=None,
                diagnostic_confidence=None,
                hint_used=False,
                isomorphic_group_id=group,
                evidence_refs=_refs(TRANSFER_KIND, transfer_pid, transfer_status),
            ),
        )
    if outcome is VerificationOutcome.SURFACE_FIX:
        original_status = _require_outcome_str(
            result.original_outcome, what="original-retry"
        )
        transfer_status = _require_outcome_str(
            result.transfer_outcome, what="transfer"
        )
        transfer_pid = context.transfer_problem_id
        assert transfer_pid is not None  # Step 10 guarantees it for PASS+non-PASS
        return (
            AttemptPlan(
                kind=ORIGINAL_KIND,
                problem_id=context.problem_id,
                variant_role=ORIGINAL_VARIANT_ROLE,
                is_transfer=False,
                passed=True,
                execution_status=original_status,
                diagnosed_misconception_id=None,
                diagnostic_confidence=None,
                hint_used=context.hint_used,
                isomorphic_group_id=group,
                evidence_refs=_refs(ORIGINAL_KIND, context.problem_id, original_status),
            ),
            AttemptPlan(
                kind=TRANSFER_KIND,
                problem_id=transfer_pid,
                variant_role=TRANSFER_VARIANT_ROLE,
                is_transfer=True,
                passed=False,
                execution_status=transfer_status,
                diagnosed_misconception_id=target,
                diagnostic_confidence=context.diagnostic_confidence,
                hint_used=False,
                isomorphic_group_id=group,
                evidence_refs=_refs(TRANSFER_KIND, transfer_pid, transfer_status),
            ),
        )
    if outcome is VerificationOutcome.NOT_IMPROVED:
        original_status = _require_outcome_str(
            result.original_outcome, what="original-retry"
        )
        return (
            AttemptPlan(
                kind=ORIGINAL_KIND,
                problem_id=context.problem_id,
                variant_role=ORIGINAL_VARIANT_ROLE,
                is_transfer=False,
                passed=False,
                execution_status=original_status,
                diagnosed_misconception_id=target,
                diagnostic_confidence=context.diagnostic_confidence,
                hint_used=context.hint_used,
                isomorphic_group_id=group,
                evidence_refs=_refs(ORIGINAL_KIND, context.problem_id, original_status),
            ),
        )
    raise ValueError(f"Unknown verification outcome {outcome!r}.")


# ---------------------------------------------------------------------------
# RecordedAttempt + LearnerStateSnapshot (immutable result parts)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RecordedAttempt:
    """One executed learner-model update (from a Step 8 transition)."""

    kind: str
    problem_id: str
    passed: bool
    execution_status: str
    is_transfer: bool
    new_mastery: float
    delta: float
    band_before: str
    band_after: str
    attempt_number: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "problem_id": self.problem_id,
            "passed": self.passed,
            "execution_status": self.execution_status,
            "is_transfer": self.is_transfer,
            "new_mastery": self.new_mastery,
            "delta": self.delta,
            "band_before": self.band_before,
            "band_after": self.band_after,
            "attempt_number": self.attempt_number,
        }


@dataclass(frozen=True)
class LearnerStateSnapshot:
    """Timestamp-free snapshot of the updated Step 8 concept view.

    Timestamps (``last_attempted_at``) and full event payloads are
    deliberately excluded so repeated integrations stay comparable and
    deterministic.
    """

    concept_id: str
    language_track: str
    mastery: float
    band: str
    attempt_count: int
    pass_count: int
    fail_count: int
    trend: str
    transfer_attempts: int
    transfer_successes: int
    hint_dependence: float
    transfer_success_rate: float
    active_misconception_ids: tuple[str, ...]

    @classmethod
    def from_concept_view(cls, view: dict[str, Any]) -> "LearnerStateSnapshot":
        if not isinstance(view, dict):
            raise TypeError(f"view must be a dict, got {type(view).__name__}.")
        return cls(
            concept_id=view["concept_id"],
            language_track=view["language_track"],
            mastery=float(view["mastery"]),
            band=view["band"],
            attempt_count=view["attempt_count"],
            pass_count=view["pass_count"],
            fail_count=view["fail_count"],
            trend=view["trend"],
            transfer_attempts=view["transfer_attempts"],
            transfer_successes=view["transfer_successes"],
            hint_dependence=float(view["hint_dependence"]),
            transfer_success_rate=float(view["transfer_success_rate"]),
            active_misconception_ids=tuple(view["active_misconception_ids"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "language_track": self.language_track,
            "mastery": self.mastery,
            "band": self.band,
            "attempt_count": self.attempt_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "trend": self.trend,
            "transfer_attempts": self.transfer_attempts,
            "transfer_successes": self.transfer_successes,
            "hint_dependence": self.hint_dependence,
            "transfer_success_rate": self.transfer_success_rate,
            "active_misconception_ids": list(self.active_misconception_ids),
        }


# ---------------------------------------------------------------------------
# ClosedLoopResult (immutable orchestration output)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClosedLoopResult:
    """Outcome of one closed-loop integration run.

    - ``verification_outcome`` echoes the Step 10 verdict (never altered).
    - ``learner_updated`` is False (with empty attempts/state/recommendations)
      for INCOMPLETE; True otherwise.
    - ``recommendations`` are Step 9 ``Recommendation`` objects (empty for
      INCOMPLETE). "Mastery achieved" is never claimed here: only Step 8's
      ``band`` is reported, verbatim, in the snapshot and reason.
    """

    verification_outcome: VerificationOutcome
    learner_updated: bool
    recorded_attempts: tuple[RecordedAttempt, ...]
    updated_state: LearnerStateSnapshot | None
    recommendations: tuple[Recommendation, ...]
    reason: str
    target_misconception_id: str | None
    concept_id: str
    language_track: str

    def __post_init__(self) -> None:
        if not isinstance(self.verification_outcome, VerificationOutcome):
            raise TypeError(
                "verification_outcome must be VerificationOutcome, "
                f"got {type(self.verification_outcome).__name__}."
            )
        _require_bool(self.learner_updated, "learner_updated")
        recorded = tuple(self.recorded_attempts)
        for item in recorded:
            if not isinstance(item, RecordedAttempt):
                raise TypeError(
                    "recorded_attempts entries must be RecordedAttempt, "
                    f"got {type(item).__name__}."
                )
        if self.updated_state is not None and not isinstance(
            self.updated_state, LearnerStateSnapshot
        ):
            raise TypeError(
                "updated_state must be LearnerStateSnapshot or None, "
                f"got {type(self.updated_state).__name__}."
            )
        recommendations = tuple(self.recommendations)
        for item in recommendations:
            if not isinstance(item, Recommendation):
                raise TypeError(
                    "recommendations entries must be Recommendation, "
                    f"got {type(item).__name__}."
                )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string.")
        if not self.learner_updated:
            if recorded:
                raise ValueError(
                    "recorded_attempts must be empty when learner_updated is False."
                )
            if recommendations:
                raise ValueError(
                    "recommendations must be empty when learner_updated is False."
                )
        object.__setattr__(self, "recorded_attempts", recorded)
        object.__setattr__(self, "recommendations", recommendations)
        object.__setattr__(self, "reason", self.reason.strip())

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping."""
        return {
            "verification_outcome": self.verification_outcome.value,
            "learner_updated": self.learner_updated,
            "recorded_attempts": [a.to_dict() for a in self.recorded_attempts],
            "updated_state": (
                self.updated_state.to_dict() if self.updated_state else None
            ),
            "recommendations": explain_recommendations(list(self.recommendations)),
            "reason": self.reason,
            "target_misconception_id": self.target_misconception_id,
            "concept_id": self.concept_id,
            "language_track": self.language_track,
        }


# ---------------------------------------------------------------------------
# Pure reason builder (deterministic; echoes Step 8's band, never invents it)
# ---------------------------------------------------------------------------
def build_closed_loop_reason(
    outcome: VerificationOutcome,
    *,
    recorded: tuple[RecordedAttempt, ...] = (),
    snapshot: LearnerStateSnapshot | None = None,
    n_recommendations: int = 0,
) -> str:
    """Build the deterministic ``ClosedLoopResult.reason`` (pure)."""
    if not isinstance(outcome, VerificationOutcome):
        raise TypeError(
            f"outcome must be VerificationOutcome, got {type(outcome).__name__}."
        )
    if outcome is VerificationOutcome.INCOMPLETE:
        return INCOMPLETE_REASON
    kinds = ", ".join(
        f"{a.kind} {'PASS' if a.passed else a.execution_status} "
        f"(attempt {a.attempt_number})"
        for a in recorded
    )
    if snapshot is not None and recorded:
        previous = round(recorded[0].new_mastery - recorded[0].delta, 4)
        state_bit = (
            f" Mastery moved {previous:.2f}->{snapshot.mastery:.2f} "
            f"(band {snapshot.band}, trend {snapshot.trend}); "
            f"attempts {snapshot.attempt_count} "
            f"({snapshot.pass_count} passed, {snapshot.fail_count} failed), "
            f"transfer {snapshot.transfer_successes}/{snapshot.transfer_attempts}."
        )
    else:
        state_bit = ""
    if outcome is VerificationOutcome.VERIFIED_IMPROVED:
        head = (
            "Verified improvement: original retry and transfer both passed; "
            f"recorded {len(recorded)} attempt(s) [{kinds}]."
        )
    elif outcome is VerificationOutcome.SURFACE_FIX:
        head = (
            "Surface fix: original retry passed but transfer did not; recorded "
            f"{len(recorded)} attempt(s) [{kinds}] and preserved the "
            "unresolved transfer weakness (no mastery claimed)."
        )
    else:  # NOT_IMPROVED
        head = (
            "Not improved: original retry did not pass; recorded "
            f"{len(recorded)} attempt(s) [{kinds}] with the target "
            "misconception preserved."
        )
    tail = f" Produced {n_recommendations} adaptive recommendation(s)."
    return (head + state_bit + tail).strip()


# ---------------------------------------------------------------------------
# Orchestration (the only function that touches the database)
# ---------------------------------------------------------------------------
def _get_journey_or_raise(session: Session, user_id: int, journey_id: int) -> Journey:
    journey = session.get(Journey, journey_id)
    if journey is None:
        raise ValueError(f"Unknown journey_id {journey_id!r}.")
    if journey.user_id != user_id:
        raise ValueError(
            f"Journey {journey_id!r} belongs to user {journey.user_id!r}, "
            f"not user {user_id!r} (tracks must not cross)."
        )
    return journey


def run_closed_loop(
    session: Session, context: ClosedLoopContext
) -> ClosedLoopResult:
    """Run VerificationResult -> Learner Model -> Adaptive Engine (orchestrates).

    Args:
        session: SQLAlchemy session (repositories flush; the caller owns
            commit/rollback, exactly like ``record_attempt`` callers).
        context: validated ``ClosedLoopContext``.

    Returns:
        Immutable ``ClosedLoopResult``. For INCOMPLETE the result carries
        no mutations and no recommendations.

    Raises:
        TypeError / ValueError: on invalid input, unknown journeys,
        language-track or concept mismatches (Python state is never
        updated from a Java attempt and vice versa).
    """
    if not isinstance(context, ClosedLoopContext):
        raise TypeError(
            f"context must be ClosedLoopContext, got {type(context).__name__}."
        )
    journey = _get_journey_or_raise(session, context.user_id, context.journey_id)
    if journey.language_track != context.language_track:
        raise ValueError(
            f"Journey {journey.id!r} track {journey.language_track!r} does not "
            f"match context track {context.language_track!r}: a "
            f"{journey.language_track} learner state must never be updated "
            f"from a {context.language_track} attempt."
        )

    result = context.verification_result
    outcome = result.outcome
    target = result.target_misconception_id

    if outcome is VerificationOutcome.INCOMPLETE:
        return ClosedLoopResult(
            verification_outcome=outcome,
            learner_updated=False,
            recorded_attempts=(),
            updated_state=None,
            recommendations=(),
            reason=INCOMPLETE_REASON,
            target_misconception_id=target,
            concept_id=context.concept_id,
            language_track=context.language_track,
        )

    # -- Step 8 mutations (owned entirely by learner_engine) ---------------
    recorded: list[RecordedAttempt] = []
    for plan in plan_records(context):
        out = learner_engine.record_attempt(
            session,
            user_id=context.user_id,
            journey_id=context.journey_id,
            concept_id=context.concept_id,
            problem_id=plan.problem_id,
            isomorphic_group_id=plan.isomorphic_group_id,
            variant_role=plan.variant_role,
            passed=plan.passed,
            execution_status=plan.execution_status,
            diagnosed_misconception_id=plan.diagnosed_misconception_id,
            diagnostic_confidence=plan.diagnostic_confidence,
            hint_used=plan.hint_used,
            evidence_refs=list(plan.evidence_refs),
            is_transfer=plan.is_transfer,
        )
        transition = out["transition"]
        recorded.append(
            RecordedAttempt(
                kind=plan.kind,
                problem_id=plan.problem_id,
                passed=plan.passed,
                execution_status=plan.execution_status,
                is_transfer=bool(transition["is_transfer"]),
                new_mastery=float(transition["new_mastery"]),
                delta=float(transition["delta"]),
                band_before=transition["band_before"],
                band_after=transition["band_after"],
                attempt_number=transition["attempt_number"],
            )
        )

    # -- Step 8 reads -> Step 9 inputs (existing adapters only) ------------
    concept_view = learner_engine.get_concept_view(
        session, context.journey_id, context.concept_id
    )
    snapshot = LearnerStateSnapshot.from_concept_view(concept_view)
    states = [ConceptState.from_learner_view(concept_view)]
    misconceptions: list[MisconceptionState] = []
    if target is not None:
        misc_view = learner_engine.get_misconception_view(
            session, context.journey_id, context.concept_id, target
        )
        misconceptions.append(MisconceptionState.from_misconception_view(misc_view))
    curriculum = context.curriculum or CurriculumInfo.from_taxonomy(context.concept_id)
    recommendations = recommend_next_actions(
        states,
        misconceptions,
        [curriculum],
        list(context.problems or ()),
        language_track=context.language_track,
    )

    reason = build_closed_loop_reason(
        outcome,
        recorded=tuple(recorded),
        snapshot=snapshot,
        n_recommendations=len(recommendations),
    )
    return ClosedLoopResult(
        verification_outcome=outcome,
        learner_updated=True,
        recorded_attempts=tuple(recorded),
        updated_state=snapshot,
        recommendations=tuple(recommendations),
        reason=reason,
        target_misconception_id=target,
        concept_id=context.concept_id,
        language_track=context.language_track,
    )


__all__ = [
    "EXECUTION_STATUS_FOR_OUTCOME",
    "INCOMPLETE_REASON",
    "ORIGINAL_KIND",
    "ORIGINAL_VARIANT_ROLE",
    "TRANSFER_KIND",
    "TRANSFER_VARIANT_ROLE",
    "AttemptPlan",
    "ClosedLoopContext",
    "ClosedLoopResult",
    "LearnerStateSnapshot",
    "RecordedAttempt",
    "build_closed_loop_reason",
    "plan_records",
    "run_closed_loop",
]
