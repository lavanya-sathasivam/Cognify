"""COGNIFY core-backend — student-facing vertical slice API (Step 16).

ORCHESTRATION ONLY (same discipline as the Step 14 journey module). This
module contains no intelligence: no execution logic, no evidence
construction, no diagnosis policy, no mastery formula, no adaptive rules,
no verification rules. Every stage delegates to an existing Steps 5-15
API:

    bank loader (Steps 12-13)
      -> evaluator + runner via ``packages.problem_bank.pipeline`` (Step 5)
      -> ``build_pack_for_submission`` (Step 6)
      -> ``diagnose_evidence`` (Steps 7 + 15: rules -> LLM -> fallback)
      -> Step 15 intervention mapping (structured object, closed vocab)
      -> ``learner_engine.record_attempt`` (Step 8)
      -> ``recommend_next_actions`` (Step 9)
      -> ``verify_improvement`` (Step 10)
      -> ``run_closed_loop`` (Step 11: Step 8 writes + Step 9 ranking)

Student flow (ONE complete vertical slice, Python C3 only):

    POST /student/sessions -> canonical problem (PY-C3-COUNT-DIV)
    POST /student/submissions (canonical, fails)
      -> execution + diagnosis + intervention + recommendations
    POST /student/submissions (canonical again = retry; passes)
      -> transfer unlocked (PY-C3-COUNT-DIV-TRANSFER)
    POST /student/submissions (transfer)
      -> execution + verification + learner update + recommendations
    GET /student/journey -> stage / verification / next recommendation

Pass/fail recording rule (mirrors the Step 14 journey, generalized): all
PASSES are recorded through the Step 11 closed loop after transfer
evidence exists; all FAILURES are recorded immediately through Step 8
with their diagnosis. Nothing is double-counted on the happy path.

Safety contract:

- The server resolves ALL problem metadata from the problem bank.
  Client-provided concept/language/mastery/diagnosis/verification values
  are ignored (request models drop unknown fields; nothing the client
  sends influences execution, diagnosis, or ranking beyond code text).
- Student code is untrusted input: it only ever flows INTO the existing
  sandbox runner abstraction. The frontend never executes code.
- Hidden test expected outputs are never serialized (the existing
  ``to_student_view`` redaction is reused; the transfer problem never
  reveals its isomorphic grouping).
- Sandbox outages fail closed (503); unknown sessions/problems fail
  loudly (404); transfer before a canonical pass is rejected (409).

Persistence limitation (preserved, not reinvented): each student session
owns one in-memory SQLite database (shared-connection pool so it survives
across requests in this process). Sessions live in a process-local store;
there is no cross-process durability and no new migration. Re-running the
same transfer submission re-records attempts (the documented Step 11
append-only behavior).
"""
from __future__ import annotations

import importlib.util
import os
import re
import secrets
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from packages import taxonomy as taxonomy_pkg
from packages.adaptive import (
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    ProblemInfo,
    recommend_next_actions,
)
from packages.problem_bank import loader as bank_loader
from packages.problem_bank import pipeline as pipe
from packages.problem_schema.models import Problem
from packages.verification import (
    VerificationContext,
    VerificationOutcome,
    verify_improvement,
)

from . import execution_client, learner_engine, repositories
from .closed_loop import ClosedLoopContext, run_closed_loop
from .db import get_session_factory, init_db

CANONICAL_ID: str = "PY-C3-COUNT-DIV"
TRANSFER_ID: str = "PY-C3-COUNT-DIV-TRANSFER"
PROBE_ID: str = "PY-C3-LOOP-MISCONCEPTION"
CONCEPT_ID: str = "C3"
LANGUAGE_TRACK: str = "python"

MAX_CODE_CHARS: int = 100_000
TIMEOUT_SECONDS: float = 5.0
MAX_VIEW_TEXT_CHARS: int = 2_000

# Step 20B read-only student views (no learning-algorithm changes).
DEFAULT_HISTORY_LIMIT: int = 20
MAX_HISTORY_LIMIT: int = 50

# Presentation grouping for the 8 concepts (Step 20B). The taxonomy owns
# concept titles/descriptions/prerequisites and has NO group field, so this
# ordering mirrors the existing frontend curriculum map
# (apps/web/src/app/lib/concepts.ts) and stays identical to it. It is
# display structure only: never an input to mastery, adaptive, or
# verification logic.
CONCEPT_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Foundations", ("C1",)),
    ("Control Flow", ("C2", "C3")),
    ("Functions", ("C4",)),
    ("Collections", ("C5", "C6")),
    ("Objects", ("C7",)),
    ("Recursion & Beyond", ("C8",)),
)
_GROUP_BY_CONCEPT: dict[str, str] = {
    cid: group for group, members in CONCEPT_GROUPS for cid in members
}

_RULE_PREFIX_RE = re.compile(r"^Rule [A-Z0-9_]+:\s*")
# Bank descriptions occasionally name the misconception they probe
# (e.g. "...probe for C3-M05..."). The catalog is student-facing, so those
# internal IDs are redacted the same way the frontend strips codes
# (see apps/web/src/app/lib/copy.ts stripCodes): meaning preserved,
# codes removed.
_MISCONCEPTION_ID_RE = re.compile(r"\bC[1-8]-M\d{2}\b")


def _safe_description(text: Any) -> Any:
    if isinstance(text, str) and _MISCONCEPTION_ID_RE.search(text):
        return _MISCONCEPTION_ID_RE.sub("this idea", text)
    return text

# Static student-facing copy per intervention type (presentation only; the
# structured Step 15 contract carries the real content and the frontend
# must not invent advice).
INTERVENTION_COPY: dict[str, str] = {
    "BOUNDARY_CHECK": "Check whether your loop processes the final required element.",
    "TRACE_LOOP": "Trace the loop for the first, middle, and last iteration.",
    "MICRO_LESSON": "Review how the loop boundary is determined.",
    "TARGETED_HINT": "Re-read the failing test and compare each step of your loop against it.",
    "REMEDIAL_PROBLEM": "Practice with a simpler variant of this loop pattern before retrying.",
}

VERIFICATION_COPY: dict[str, str] = {
    "VERIFIED_IMPROVED": (
        "Nice! You solved the original problem and successfully applied "
        "the same idea to a new problem."
    ),
    "SURFACE_FIX": (
        "Good progress on the original problem. The new problem still "
        "needs work — try applying the same fix there."
    ),
    "NOT_IMPROVED": (
        "Not quite yet — the original problem still needs a passing "
        "solution. Review the feedback and retry."
    ),
    "INCOMPLETE": (
        "Verification is incomplete — submit both the retry and the "
        "transfer solution first."
    ),
}

RunnerFactory = Callable[[str, float], Any]


# ---------------------------------------------------------------------------
# Step 15 intervention mapping (reused in-process via alias loading)
# ---------------------------------------------------------------------------
# Path anchor: the repo/image root is the parent of ``packages/``. Resolving
# from the imported pipeline module (not ``__file__``) keeps this working
# both in the repo checkout (services/core-backend/app/student.py) and in
# the Docker image (where only app/ is copied to ./app but packages/ and
# services/ sit beside it under /code).
_REPO_ROOT = Path(pipe.__file__).resolve().parents[2]
_AI_APP_DIR = _REPO_ROOT / "services" / "ai-service" / "app"
_AI_ALIAS = "cognify_ai_app"


def _ensure_ai_package() -> None:
    if _AI_ALIAS in sys.modules:
        return
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    init_file = _AI_APP_DIR / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        _AI_ALIAS, init_file, submodule_search_locations=[str(_AI_APP_DIR)]
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot create module spec for {_AI_ALIAS}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_AI_ALIAS] = module
    spec.loader.exec_module(module)


def _ai_interventions_module() -> Any:
    """Existing Step 15 intervention mapper (never reimplemented here)."""
    full_name = _AI_ALIAS + ".interventions"
    if full_name in sys.modules:
        return sys.modules[full_name]
    _ensure_ai_package()
    if full_name in sys.modules:  # loaded as a side effect (relative import)
        return sys.modules[full_name]
    target = _AI_APP_DIR / "interventions.py"
    spec = importlib.util.spec_from_file_location(full_name, target)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot create module spec for {full_name}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def _default_runner_factory(language: str, timeout_seconds: float) -> Any:
    """Production factory sentinel (HTTP execution; never Docker).

    Production submissions execute via execution-service over HTTP
    (see ``execution_client.execute_problem``). This factory is retained
    for backwards compatibility and for ``_execute`` dispatch, but it
    never creates a local Docker runner. Direct invocation fails closed
    so core-backend can never accidentally instantiate
    ``DockerSandboxRunner`` (core-backend has no Docker access).
    """
    if language != LANGUAGE_TRACK:
        raise ValueError(
            f"Unsupported language {language!r} in this slice (python only)."
        )
    raise RuntimeError(
        "Local execution is disabled in core-backend; submissions execute "
        "via execution-service over HTTP (execution_client.execute_problem)."
    )


# ---------------------------------------------------------------------------
# Session store (process-local, in-memory prototype persistence)
# ---------------------------------------------------------------------------
@dataclass
class _StudentSession:
    engine: Any
    user_id: int
    journey_id: int
    language_track: str
    canonical_id: str = CANONICAL_ID
    transfer_id: str = TRANSFER_ID
    canonical_pass_result: Any = None
    last_diagnosis_mid: str | None = None
    verification: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] = field(default_factory=list)


class StudentStore:
    """Process-local student sessions (prototype persistence)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, _StudentSession] = {}

    def create(self, language_track: str) -> tuple[str, _StudentSession]:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        init_db(engine)
        session = get_session_factory(engine)()
        try:
            user = repositories.create_user(session)
            journey = repositories.create_journey(session, user.id, language_track)
            session.commit()
            record = _StudentSession(
                engine=engine,
                user_id=user.id,
                journey_id=journey.id,
                language_track=journey.language_track,
            )
        finally:
            session.close()
        session_id = secrets.token_urlsafe(24)
        with self._lock:
            self._sessions[session_id] = record
        return session_id, record

    def get(self, session_id: str) -> _StudentSession:
        with self._lock:
            record = self._sessions.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown session_id.")
        return record


# ---------------------------------------------------------------------------
# Request models (unknown client fields are ignored, never trusted)
# ---------------------------------------------------------------------------
class SessionCreate(BaseModel):
    model_config = {"extra": "ignore"}

    language_track: str = LANGUAGE_TRACK


class SubmissionCreate(BaseModel):
    model_config = {"extra": "ignore"}

    session_id: str
    problem_id: str
    code: str


# ---------------------------------------------------------------------------
# Safe student-facing views (no hidden answers, no internals)
# ---------------------------------------------------------------------------
def problem_view(problem: Problem) -> dict[str, Any]:
    """Safe problem metadata (tests and bank internals never serialized)."""
    return {
        "problem_id": problem.problem_id,
        "language": problem.language,
        "concept_id": problem.concept_id,
        "title": problem.title,
        "statement": problem.description,
        "constraints": list(problem.constraints),
        "input_format": problem.input_format,
        "output_format": problem.output_format,
        "starter_code": problem.starter_code,
        "difficulty": problem.difficulty,
    }


def _truncate_text(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_VIEW_TEXT_CHARS:
        return value[:MAX_VIEW_TEXT_CHARS] + "...[truncated]"
    return value


def execution_view(problem: Problem, result: Any) -> dict[str, Any]:
    """Existing redacted student view + output-size guard (copy only)."""
    view = pipe.to_student_view(problem, result)
    for key in ("stdout", "stderr", "expected_output", "actual_output"):
        view[key] = _truncate_text(view.get(key))
    for entry in view.get("tests", []):
        for key in ("input", "expected_output", "actual_output", "stdout", "stderr"):
            entry[key] = _truncate_text(entry.get(key))
    return view


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.70:
        return "likely"
    if confidence >= 0.50:
        return "possible"
    return "uncertain"


def diagnosis_view(diagnosis: Any, failed_test_id: str | None) -> dict[str, Any] | None:
    """Student-safe diagnosis (rule-ID prefix stripped, certainty labeled)."""
    if diagnosis is None:
        return None
    raw_explanation = str(diagnosis.explanation)
    cleaned = _RULE_PREFIX_RE.sub("", raw_explanation).strip() or raw_explanation
    confidence = float(diagnosis.confidence)
    return {
        "misconception_id": diagnosis.misconception_id,
        "explanation": cleaned,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "evidence_summary": {
            "failed_test_id": failed_test_id,
        },
        "source": diagnosis.source,
    }


def intervention_view(intervention: Any) -> dict[str, Any] | None:
    if intervention is None:
        return None
    body = intervention.to_dict()
    body["student_message"] = INTERVENTION_COPY.get(body["intervention_type"], "")
    return body


def recommendation_view(rec: dict[str, Any]) -> dict[str, Any]:
    problem_id = rec.get("problem_id")
    title: str | None = None
    if problem_id is not None:
        try:
            title = bank_loader.load_problem(problem_id).title
        except (ValueError, TypeError):
            title = None
    return {
        "action": rec.get("action_type"),
        "reason": rec.get("reason"),
        "problem_id": problem_id,
        "problem_title": title,
    }


def verification_view(result: Any) -> dict[str, Any]:
    outcome = result.outcome.value
    return {
        "outcome": outcome,
        "message": VERIFICATION_COPY.get(outcome, VERIFICATION_COPY["INCOMPLETE"]),
    }


# ---------------------------------------------------------------------------
# Step 20B read-only student views (delegate to existing engines only)
# ---------------------------------------------------------------------------
def _group_for_concept(concept_id: str) -> str:
    """Presentation group for a concept (display only, never algorithmic)."""
    return _GROUP_BY_CONCEPT.get(concept_id.strip().upper(), "Other")


def _concept_card(concept_id: str, view: dict[str, Any]) -> dict[str, Any]:
    """Student-safe per-concept card (no mastery floats, no internal IDs).

    Reads taxonomy metadata (title/description/prerequisites) plus the
    existing learner-engine view. Not-started concepts (zero attempts)
    report honestly with ``status == "not_started"``; nothing is
    fabricated. Active misconception IDs, isomorphic grouping, mastery
    decimals, and evidence refs are deliberately omitted student-side.
    """
    concept = taxonomy_pkg.get_concept(concept_id)
    transfer = view.get("transfer_breakdown", {}) or {}
    recent = view.get("recent_history", []) or []
    attempt_count = int(view.get("attempt_count", 0))
    band = str(view.get("band", "unknown"))
    return {
        "concept_id": concept.id,
        "title": concept.title,
        "description": concept.description,
        "group": _group_for_concept(concept.id),
        "prerequisites": list(concept.prerequisites),
        "status": "not_started" if attempt_count == 0 else "started",
        "band": band,
        "mastery_claim": band == "mastered",
        "trend": view.get("trend", "unknown"),
        "attempt_count": attempt_count,
        "pass_count": int(view.get("pass_count", 0)),
        "fail_count": int(view.get("fail_count", 0)),
        "transfer": {
            "attempts": int(transfer.get("attempts", 0)),
            "successes": int(transfer.get("successes", 0)),
            "failures": int(transfer.get("failures", 0)),
            "success_rate": float(transfer.get("success_rate", 0.0)),
        },
        "hint_dependence": float(view.get("hint_dependence", 0.0)),
        "hint_count": int(view.get("hint_count", 0)),
        "recent_history": [
            {
                "problem_id": entry.get("problem_id"),
                "passed": bool(entry.get("passed", False)),
                "is_transfer": bool(entry.get("is_transfer", False)),
                "hint_used": bool(entry.get("hint_used", False)),
            }
            for entry in recent[-3:]
        ],
        "active_misconception_count": len(view.get("active_misconception_ids", [])),
    }


def _next_action_view(rec: dict[str, Any], concept_id: str) -> dict[str, Any]:
    """Student view of one adaptive recommendation (existing engine output).

    Keeps the established Practice contract (action code + reason text for
    frontend humanization, safe problem title) and adds the owning
    concept so per-concept pages can attribute it. No adaptive rules live
    here: the caller must supply ``explain_recommendations`` output.
    """
    problem_id = rec.get("problem_id")
    title: str | None = None
    if problem_id is not None:
        try:
            title = bank_loader.load_problem(problem_id).title
        except (ValueError, TypeError):
            title = None
    return {
        "action": rec.get("action_type"),
        "reason": rec.get("reason"),
        "problem_id": problem_id,
        "problem_title": title,
        "concept_id": concept_id,
    }


def _full_problem_catalog() -> list[ProblemInfo]:
    """Whole-bank adaptive catalog (discovers future problems via loader)."""
    catalog: list[ProblemInfo] = []
    for problem in bank_loader.load_all_problems().values():
        catalog.append(
            ProblemInfo.from_dict(
                {
                    "problem_id": problem.problem_id,
                    "concept_id": problem.concept_id,
                    "difficulty": problem.difficulty,
                    "isomorphic_group_id": problem.isomorphic_group_id,
                    "variant_role": problem.variant_role,
                }
            )
        )
    return catalog


def _human_issue_summary(misconception_id: str) -> str:
    """Student-safe one-liner for a diagnosed issue (never leaks the ID)."""
    try:
        name = taxonomy_pkg.get_misconception(misconception_id).name
    except (KeyError, ValueError, TypeError):
        return "An issue was identified — review the feedback and retry."
    words = str(name).replace("-", " ").replace("_", " ").strip() or "this idea"
    label = words[0].upper() + words[1:]
    return f"{label} identified — review the feedback and retry."


def _history_feedback(
    *, passed: bool, is_transfer: bool, execution_status: str, misconception_id: str | None
) -> str:
    """Human sentence for one attempt (presentation only, no logic)."""
    if passed:
        if is_transfer:
            return "Solved correctly in a new context."
        return "Solved correctly."
    if misconception_id:
        return _human_issue_summary(misconception_id)
    if execution_status in ("RUNTIME_ERROR", "COMPILE_ERROR", "TIMEOUT"):
        return "Needs another attempt — the code didn't run cleanly."
    return "Needs another attempt — review the feedback and retry."


# ---------------------------------------------------------------------------
# Orchestration helpers (delegate to existing APIs only)
# ---------------------------------------------------------------------------
def _catalog() -> list[ProblemInfo]:
    problems = [
        bank_loader.load_problem(CANONICAL_ID),
        bank_loader.load_problem(TRANSFER_ID),
        bank_loader.load_problem(PROBE_ID),
    ]
    return [
        ProblemInfo.from_dict(
            {
                "problem_id": p.problem_id,
                "concept_id": p.concept_id,
                "difficulty": p.difficulty,
                "isomorphic_group_id": p.isomorphic_group_id,
                "variant_role": p.variant_role,
            }
        )
        for p in problems
    ]


def _intervention_recommendations(
    db_session: Session,
    record: _StudentSession,
    diagnosed_mid: str | None,
) -> list[dict[str, Any]]:
    concept_view = learner_engine.get_concept_view(
        db_session, record.journey_id, CONCEPT_ID
    )
    states = [ConceptState.from_learner_view(concept_view)]
    misconceptions: list[MisconceptionState] = []
    if diagnosed_mid is not None:
        misc_view = learner_engine.get_misconception_view(
            db_session, record.journey_id, CONCEPT_ID, diagnosed_mid
        )
        misconceptions.append(MisconceptionState.from_misconception_view(misc_view))
    ranked = recommend_next_actions(
        states,
        misconceptions,
        [CurriculumInfo.from_taxonomy(CONCEPT_ID)],
        _catalog(),
        language_track=record.language_track,
    )
    from packages.adaptive import explain_recommendations

    return [recommendation_view(r) for r in explain_recommendations(ranked)]


def _journey_state(
    db_session: Session, record: _StudentSession
) -> dict[str, Any]:
    view = learner_engine.get_concept_view(db_session, record.journey_id, CONCEPT_ID)
    band = view["band"]
    if record.verification is not None:
        stage = "transfer_done"
    elif record.canonical_pass_result is not None:
        stage = "retry_passed"
    elif view["attempt_count"] > 0:
        stage = "practicing"
    else:
        stage = "started"
    return {
        "stage": stage,
        "canonical_passed": record.canonical_pass_result is not None,
        "transfer_available": record.canonical_pass_result is not None,
        "band": band,
        "mastery_claim": band == "mastered",
    }


def _resolve_problem(problem_id: str, record: _StudentSession) -> tuple[Problem, str]:
    """Load the problem server-side; classify its journey role."""
    if problem_id == record.canonical_id:
        role = "canonical"
    elif problem_id == record.transfer_id:
        role = "transfer"
    else:
        raise HTTPException(
            status_code=422,
            detail=f"problem_id {problem_id!r} is not part of this learning journey.",
        )
    try:
        problem = bank_loader.load_problem(problem_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if problem.language != record.language_track:
        raise HTTPException(
            status_code=422,
            detail=f"Problem language {problem.language!r} does not match "
            f"session track {record.language_track!r}.",
        )
    return problem, role


def _execute(
    problem: Problem, code: str, runner_factory: RunnerFactory | None) -> Any:
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=422, detail="code must be a non-empty string.")
    if len(code) > MAX_CODE_CHARS:
        raise HTTPException(
            status_code=422, detail=f"code exceeds {MAX_CODE_CHARS} characters."
        )
    # Production path: default factory (or None) executes via
    # execution-service over HTTP. core-backend never instantiates a
    # local Docker runner here.
    if runner_factory is None or runner_factory is _default_runner_factory:
        if problem.language != LANGUAGE_TRACK:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unsupported language {problem.language!r} "
                    "in this slice (python only)."
                ),
            )
        try:
            return execution_client.execute_problem(
                problem, code, timeout_seconds=TIMEOUT_SECONDS
            )
        except execution_client.ExecutionServiceUnavailable as exc:
            raise HTTPException(
                status_code=503, detail="Execution backend unavailable."
            ) from exc
        except execution_client.ExecutionServiceBadResponse as exc:
            raise HTTPException(
                status_code=502,
                detail="Execution backend returned an invalid response.",
            ) from exc
    # Injected/test path: existing local runner via the pipeline
    # (FakeSandboxRunner / MarkerRunner in tests).
    try:
        assert runner_factory is not None
        runner = runner_factory(problem.language, TIMEOUT_SECONDS)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if runner is None or not hasattr(runner, "run_single"):
        raise HTTPException(status_code=500, detail="Execution backend misconfigured.")
    try:
        return pipe.execute_problem(
            problem, code, runner, timeout_seconds=TIMEOUT_SECONDS
        )
    except Exception as exc:
        mods = pipe.execution_modules()
        unavailable = mods["sandbox"].SandboxUnavailableError
        if isinstance(exc, unavailable):
            raise HTTPException(
                status_code=503, detail="Execution backend unavailable."
            ) from exc
        raise


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------
def create_student_router(
    store: StudentStore,
    *,
    runner_factory: RunnerFactory | None = None,
    llm_client: Any = None,
) -> APIRouter:
    """Build the student-facing routes bound to one session store."""
    factory = runner_factory or _default_runner_factory
    router = APIRouter(prefix="/student", tags=["student"])

    def _db_session(record: _StudentSession) -> Session:
        return get_session_factory(record.engine)()

    @router.post("/sessions")
    def create_session(body: SessionCreate) -> dict[str, Any]:
        track = body.language_track.strip().lower() if body.language_track else ""
        if track != LANGUAGE_TRACK:
            raise HTTPException(
                status_code=422,
                detail=f"Only {LANGUAGE_TRACK!r} is supported in this slice.",
            )
        session_id, record = store.create(track)
        problem = bank_loader.load_problem(record.canonical_id)
        db_session = _db_session(record)
        try:
            state = _journey_state(db_session, record)
        finally:
            db_session.close()
        return {
            "session_id": session_id,
            "language_track": record.language_track,
            "journey_state": state,
            "problem": problem_view(problem),
        }

    @router.get("/problems/{problem_id}")
    def get_problem(problem_id: str, session_id: str) -> dict[str, Any]:
        record = store.get(session_id)
        problem, _role = _resolve_problem(problem_id.strip(), record)
        return problem_view(problem)

    @router.post("/submissions")
    def submit(body: SubmissionCreate) -> dict[str, Any]:
        record = store.get(body.session_id)
        problem, role = _resolve_problem(body.problem_id.strip(), record)
        result = _execute(problem, body.code, factory)
        status = pipe.execution_status_str(result)
        exec_view = execution_view(problem, result)

        if role == "transfer":
            return _submit_transfer(
                record, body.session_id, problem, result, exec_view
            )

        db_session = _db_session(record)
        try:
            if status == "PASSED":
                # Passes are recorded through the closed loop after transfer
                # evidence exists (Step 11 contract); unlock transfer now.
                record.canonical_pass_result = result
                record.last_diagnosis_mid = None
                db_session.commit()
                transfer_problem = bank_loader.load_problem(record.transfer_id)
                state = _journey_state(db_session, record)
                return {
                    "session_id": body.session_id,
                    "problem_id": problem.problem_id,
                    "variant_role": role,
                    "outcome": status,
                    "execution": exec_view,
                    "diagnosis": None,
                    "intervention": None,
                    "recommendations": [],
                    "transfer_available": True,
                    "transfer_problem": problem_view(transfer_problem),
                    "verification": None,
                    "journey_state": state,
                }
            if status == "FAILED":
                snapshot = learner_engine.snapshot_for_evidence(
                    db_session, record.user_id, record.journey_id, CONCEPT_ID
                )
                pack = pipe.build_pack_for_submission(
                    body.code, problem, result, snapshot
                )
                diagnosis = pipe.diagnose_evidence(pack, llm_client)
                learner_engine.record_attempt(
                    db_session,
                    user_id=record.user_id,
                    journey_id=record.journey_id,
                    concept_id=CONCEPT_ID,
                    problem_id=problem.problem_id,
                    isomorphic_group_id=problem.isomorphic_group_id,
                    variant_role=problem.variant_role,
                    passed=False,
                    execution_status=status,
                    diagnosed_misconception_id=diagnosis.misconception_id,
                    diagnostic_confidence=diagnosis.confidence,
                    hint_used=False,
                    evidence_refs=list(diagnosis.evidence_refs),
                    is_transfer=False,
                )
                interventions = _ai_interventions_module()
                intervention = interventions.build_intervention(
                    diagnosis.to_dict(), pack
                )
                record.last_diagnosis_mid = diagnosis.misconception_id
                recommendations = _intervention_recommendations(
                    db_session, record, diagnosis.misconception_id
                )
                record.recommendations = recommendations
                db_session.commit()
                state = _journey_state(db_session, record)
                return {
                    "session_id": body.session_id,
                    "problem_id": problem.problem_id,
                    "variant_role": role,
                    "outcome": status,
                    "execution": exec_view,
                    "diagnosis": diagnosis_view(diagnosis, pack.failed_test_id),
                    "intervention": intervention_view(intervention),
                    "recommendations": recommendations,
                    "transfer_available": False,
                    "transfer_problem": None,
                    "verification": None,
                    "journey_state": state,
                }
            # Error statuses (RUNTIME_ERROR/TIMEOUT/COMPILE_ERROR): record
            # the failed attempt without a diagnosis (nothing meaningful to
            # diagnose from a crash/hang); surface safe error information.
            learner_engine.record_attempt(
                db_session,
                user_id=record.user_id,
                journey_id=record.journey_id,
                concept_id=CONCEPT_ID,
                problem_id=problem.problem_id,
                isomorphic_group_id=problem.isomorphic_group_id,
                variant_role=problem.variant_role,
                passed=False,
                execution_status=status,
                diagnosed_misconception_id=None,
                diagnostic_confidence=None,
                hint_used=False,
                evidence_refs=[],
                is_transfer=False,
            )
            recommendations = _intervention_recommendations(db_session, record, None)
            record.recommendations = recommendations
            db_session.commit()
            state = _journey_state(db_session, record)
            return {
                "session_id": body.session_id,
                "problem_id": problem.problem_id,
                "variant_role": role,
                "outcome": status,
                "execution": exec_view,
                "diagnosis": None,
                "intervention": None,
                "recommendations": recommendations,
                "transfer_available": record.canonical_pass_result is not None,
                "transfer_problem": None,
                "verification": None,
                "journey_state": state,
            }
        finally:
            db_session.close()

    def _submit_transfer(
        record: _StudentSession,
        session_id: str,
        problem: Problem,
        result: Any,
        exec_view: dict[str, Any],
    ) -> dict[str, Any]:
        if record.canonical_pass_result is None:
            raise HTTPException(
                status_code=409,
                detail="Transfer is unavailable: pass the canonical problem first.",
            )
        status = pipe.execution_status_str(result)
        canonical = bank_loader.load_problem(record.canonical_id)
        original_retry = pipe.attempt_from_execution(
            canonical,
            record.canonical_pass_result,
            misconception_id=record.last_diagnosis_mid,
        )
        transfer_attempt = pipe.attempt_from_execution(
            problem, result, is_transfer=True
        )
        context = VerificationContext(
            original_problem_id=canonical.problem_id,
            transfer_problem_id=problem.problem_id,
            concept_id=CONCEPT_ID,
            language_track=record.language_track,
            target_misconception_id=record.last_diagnosis_mid,
            original_retry=original_retry,
            transfer=transfer_attempt,
            isomorphic_group_id=canonical.isomorphic_group_id,
        )
        verification_result = verify_improvement(context)
        db_session = _db_session(record)
        try:
            loop_context = ClosedLoopContext(
                user_id=record.user_id,
                journey_id=record.journey_id,
                language_track=record.language_track,
                concept_id=CONCEPT_ID,
                problem_id=canonical.problem_id,
                transfer_problem_id=problem.problem_id,
                verification_result=verification_result,
                problems=_catalog(),
            )
            loop_result = run_closed_loop(db_session, loop_context)
            db_session.commit()
            verification = verification_view(verification_result)
            record.verification = verification
            from packages.adaptive import explain_recommendations

            recommendations = [
                recommendation_view(r)
                for r in explain_recommendations(list(loop_result.recommendations))
            ]
            record.recommendations = recommendations
            state = _journey_state(db_session, record)
        finally:
            db_session.close()
        return {
            "session_id": session_id,
            "problem_id": problem.problem_id,
            "variant_role": "transfer",
            "outcome": status,
            "execution": exec_view,
            "diagnosis": None,
            "intervention": None,
            "recommendations": recommendations,
            "transfer_available": True,
            "transfer_problem": None,
            "verification": verification,
            "journey_state": state,
        }

    @router.get("/journey")
    def get_journey(session_id: str) -> dict[str, Any]:
        record = store.get(session_id)
        db_session = _db_session(record)
        try:
            state = _journey_state(db_session, record)
        finally:
            db_session.close()
        return {
            "session_id": session_id,
            "language_track": record.language_track,
            "canonical_problem_id": record.canonical_id,
            "transfer_problem_id": record.transfer_id,
            "journey_state": state,
            "verification": record.verification,
            "recommendations": record.recommendations,
        }

    @router.get("/concepts")
    def get_concepts(session_id: str) -> dict[str, Any]:
        """READ-ONLY per-concept learner state for all 8 concepts (Step 20B).

        Delegates to the existing taxonomy (metadata) + learner-engine
        views (state) + adaptive engine (next action). Never writes:
        no ``record_attempt``, no events, no commits — the session is
        rolled back before returning so repeated GETs cannot change
        learner state.
        """
        record = store.get(session_id)
        db_session = _db_session(record)
        try:
            views: dict[str, dict[str, Any]] = {}
            for cid in taxonomy_pkg.list_concept_ids():
                views[cid] = learner_engine.get_concept_view(
                    db_session, record.journey_id, cid
                )
            concepts = [_concept_card(cid, views[cid]) for cid in views]
            # Existing adaptive engine over the full curriculum (no
            # duplicated rules): states + active misconceptions + taxonomy
            # curricula + whole-bank catalog.
            states = [ConceptState.from_learner_view(v) for v in views.values()]
            misconceptions: list[MisconceptionState] = []
            for cid, view in views.items():
                for mid in view.get("active_misconception_ids", []):
                    misc_view = learner_engine.get_misconception_view(
                        db_session, record.journey_id, cid, mid
                    )
                    misconceptions.append(
                        MisconceptionState.from_misconception_view(misc_view)
                    )
            curricula = [
                CurriculumInfo.from_taxonomy(cid) for cid in views
            ]
            from packages.adaptive import explain_recommendations

            ranked = recommend_next_actions(
                states,
                misconceptions,
                curricula,
                _full_problem_catalog(),
                language_track=record.language_track,
            )
            explained = explain_recommendations(ranked)
            next_action: dict[str, Any] | None = None
            if explained:
                top = explained[0]
                next_action = _next_action_view(top, str(top.get("concept_id")))
            return {
                "session_id": session_id,
                "language_track": record.language_track,
                "concepts": concepts,
                "next_action": next_action,
            }
        finally:
            db_session.rollback()
            db_session.close()

    @router.get("/history")
    def get_history(session_id: str, limit: int = DEFAULT_HISTORY_LIMIT) -> dict[str, Any]:
        """READ-ONLY student-safe learning history (Step 20B).

        Built from the existing append-only attempt events only — no
        parallel store. Whitelisted fields: hidden test outputs,
        reference solutions, misconception IDs, isomorphic grouping, and
        evidence refs are never serialized. Never writes (rollback
        before returning).
        """
        if type(limit) is not int or limit < 1:
            raise HTTPException(
                status_code=422, detail="limit must be a positive int."
            )
        capped = min(limit, MAX_HISTORY_LIMIT)
        record = store.get(session_id)
        db_session = _db_session(record)
        try:
            events = repositories.list_events_for_journey(
                db_session, record.journey_id, event_type="attempt"
            )
            total = len(events)
            tail = events[-capped:] if total else []
            verified_outcome = (record.verification or {}).get("outcome")
            items: list[dict[str, Any]] = []
            for index, event in enumerate(tail, start=total - len(tail) + 1):
                meta = dict(event.event_metadata or {})
                problem_id = meta.get("problem_id")
                concept_id = event.concept_id
                try:
                    problem_title = (
                        bank_loader.load_problem(problem_id).title
                        if isinstance(problem_id, str) and problem_id
                        else None
                    )
                except (ValueError, TypeError):
                    problem_title = None
                try:
                    concept_title = taxonomy_pkg.get_concept(concept_id).title
                except (KeyError, ValueError, TypeError):
                    concept_title = None
                passed = bool(meta.get("passed", meta.get("success", False)))
                status = str(meta.get("execution_status", "")).strip().upper()
                is_transfer = bool(meta.get("is_transfer", False))
                mid = event.misconception_id
                created = event.created_at
                items.append(
                    {
                        "order": index,
                        "created_at": created.isoformat() if created is not None else None,
                        "problem_id": problem_id,
                        "problem_title": problem_title,
                        "concept_id": concept_id,
                        "concept_title": concept_title,
                        "outcome": "passed" if passed else "failed",
                        "execution_status": status,
                        "is_transfer": is_transfer,
                        "feedback": _history_feedback(
                            passed=passed,
                            is_transfer=is_transfer,
                            execution_status=status,
                            misconception_id=mid,
                        ),
                        "verified": bool(
                            passed
                            and is_transfer
                            and verified_outcome == "VERIFIED_IMPROVED"
                        ),
                    }
                )
            return {
                "session_id": session_id,
                "total": total,
                "limit": capped,
                "items": items,
            }
        finally:
            db_session.rollback()
            db_session.close()

    @router.get("/problems")
    def list_problems(session_id: str) -> dict[str, Any]:
        """READ-ONLY safe problem catalog from the existing bank (Step 20B).

        Discovered via ``load_all_problems`` so future bank additions
        appear with no endpoint change. Exposes metadata only: no test
        cases, no hidden outputs, no misconception bindings, no
        isomorphic grouping (kept hidden per the submission safety
        contract), no reference solutions.
        """
        record = store.get(session_id)
        entries: list[dict[str, Any]] = []
        for problem in bank_loader.load_all_problems().values():
            try:
                concept_title = taxonomy_pkg.get_concept(problem.concept_id).title
            except (KeyError, ValueError, TypeError):
                concept_title = None
            entries.append(
                {
                    "problem_id": problem.problem_id,
                    "title": problem.title,
                    "language": problem.language,
                    "concept_id": problem.concept_id,
                    "concept_title": concept_title,
                    "difficulty": problem.difficulty,
                    "role": problem.variant_role,
                    "description": _safe_description(problem.description),
                }
            )
        return {
            "session_id": session_id,
            "language_track": record.language_track,
            "total": len(entries),
            "problems": entries,
        }

    return router


__all__ = [
    "CANONICAL_ID",
    "CONCEPT_ID",
    "INTERVENTION_COPY",
    "LANGUAGE_TRACK",
    "PROBE_ID",
    "TRANSFER_ID",
    "VERIFICATION_COPY",
    "SessionCreate",
    "StudentStore",
    "SubmissionCreate",
    "CONCEPT_GROUPS",
    "DEFAULT_HISTORY_LIMIT",
    "MAX_HISTORY_LIMIT",
    "create_student_router",
    "diagnosis_view",
    "execution_view",
    "intervention_view",
    "problem_view",
    "recommendation_view",
    "verification_view",
]
