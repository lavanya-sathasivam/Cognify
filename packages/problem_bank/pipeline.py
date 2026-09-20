"""COGNIFY problem_bank — execution integration (Step 12).

Connects, without rewriting anything:

    Problem Bank (loader + ``problem-bank/python/*.json``)
        -> execution-service evaluator + sandbox runners (Step 5, reused)
        -> EvidencePack builder (Step 6, reused)
        -> AI diagnosis service with fallback (Step 7, reused)
        -> verification engine + closed-loop planning (Steps 10/11, reused)

OWNERSHIP (this module coordinates; it duplicates nothing):
- Execution owns code execution, test comparison, terminal statuses, and
  sandbox isolation. All runs go through the existing
  ``services/execution-service/app/evaluator.evaluate`` plus the existing
  ``PythonRunner``/``SandboxRunner`` classes. No new runner, no new
  sandbox, no host execution.
- Evidence owns pack construction (``packages.evidence``). This module
  only forwards (code, problem, execution result, learner snapshot).
- Diagnosis owns misconception identification (``services/ai-service``).
  This module only forwards the pack; with no LLM configured the
  existing deterministic fallback answers (``client=None``).
- Verification owns improvement verdicts (``packages.verification``);
  closed-loop planning owns learner-update plans
  (``services/core-backend/app/closed_loop.plan_records``, pure).
  Verification inputs are built ONLY from actual execution results —
  nothing is fabricated, and ``run_closed_loop`` (DB writes) is never
  called here.

SERVICE LOADING: the three services live in hyphenated directories
(``services/execution-service`` etc.) that are not importable as packages,
and each exposes a top-level ``app`` package, so importing two of them as
``app.*`` in one process would collide. This module therefore loads them
under distinct aliases (``cognify_exec_app``, ``cognify_ai_app``,
``cognify_core_app``) via explicit file locations. The loaded code is the
existing service code, unmodified.

Determinism: no clock, no randomness, no UUIDs here. Repeated runs with
the same scripted sandbox return equal ``to_dict()`` results (production
Docker runs vary only in ``time_ms``/wall-clock, which this module never
invents).

Security: no subprocess, no shell, no network, no filesystem writes, no
environment reads, no secret handling in this module. Student code is
only ever passed INTO the existing sandbox abstraction.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

from packages.evidence.builder import build_evidence_pack
from packages.evidence.models import (
    ConceptStateSnapshot,
    EvidencePack,
    LearnerSnapshot,
)
from packages.problem_schema.models import Problem
from packages.verification import (
    ExecutionOutcome,
    VerificationAttempt,
    normalize_execution_outcome,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXEC_APP_DIR = _REPO_ROOT / "services" / "execution-service" / "app"
_AI_APP_DIR = _REPO_ROOT / "services" / "ai-service" / "app"
_CORE_APP_DIR = _REPO_ROOT / "services" / "core-backend" / "app"

DEFAULT_TIMEOUT_SECONDS: float = 5.0

# Execution-service status -> verification outcome (explicit bridge; the
# three error statuses are spelled identically on both sides, while the
# pass/fail pair differs: PASSED/PASS, FAILED/FAIL).
EXECUTION_TO_VERIFICATION_OUTCOME: dict[str, str] = {
    "PASSED": "PASS",
    "FAILED": "FAIL",
    "COMPILE_ERROR": "COMPILE_ERROR",
    "RUNTIME_ERROR": "RUNTIME_ERROR",
    "TIMEOUT": "TIMEOUT",
}

_ALIAS_CACHE: dict[str, Any] = {}


def _ensure_alias_package(alias: str, app_dir: Path) -> Any:
    """Register ``alias`` as a package pointing at ``app_dir`` (idempotent)."""
    if alias in sys.modules:
        return sys.modules[alias]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    init_file = app_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        alias, init_file, submodule_search_locations=[str(app_dir)]
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot create module spec for {alias} at {app_dir}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _load_service_module(alias: str, app_dir: Path, module_name: str) -> Any:
    """Load ``app_dir/module_name.py`` as ``alias.module_name`` (cached)."""
    full_name = alias + "." + module_name
    if full_name in sys.modules:
        return sys.modules[full_name]
    _ensure_alias_package(alias, app_dir)
    if full_name in sys.modules:  # loaded as a side effect (relative import)
        return sys.modules[full_name]
    target = app_dir / (module_name + ".py")
    if not target.is_file():
        raise ImportError(f"Service module missing: {target}.")
    spec = importlib.util.spec_from_file_location(full_name, target)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot create module spec for {full_name}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def execution_modules() -> dict[str, Any]:
    """Existing execution-service modules (evaluator/sandbox/runners)."""
    if "exec" not in _ALIAS_CACHE:
        _ALIAS_CACHE["exec"] = {
            "evaluator": _load_service_module(
                "cognify_exec_app", _EXEC_APP_DIR, "evaluator"
            ),
            "sandbox": _load_service_module(
                "cognify_exec_app", _EXEC_APP_DIR, "sandbox"
            ),
            "python_runner": _load_service_module(
                "cognify_exec_app", _EXEC_APP_DIR, "python_runner"
            ),
        }
    return _ALIAS_CACHE["exec"]


def ai_service_module() -> Any:
    """Existing AI diagnosis orchestrator (``diagnose_pack``)."""
    if "ai_service" not in _ALIAS_CACHE:
        _ALIAS_CACHE["ai_service"] = _load_service_module(
            "cognify_ai_app", _AI_APP_DIR, "service"
        )
    return _ALIAS_CACHE["ai_service"]


def ai_main_module() -> Any:
    """Existing AI HTTP API (``create_app``) for the /diagnose reach test."""
    if "ai_main" not in _ALIAS_CACHE:
        _ALIAS_CACHE["ai_main"] = _load_service_module(
            "cognify_ai_app", _AI_APP_DIR, "main"
        )
    return _ALIAS_CACHE["ai_main"]


def ai_llm_client_module() -> Any:
    """Existing LLM client fakes (Mock/Unavailable) for deterministic tests."""
    if "ai_llm" not in _ALIAS_CACHE:
        _ALIAS_CACHE["ai_llm"] = _load_service_module(
            "cognify_ai_app", _AI_APP_DIR, "llm_client"
        )
    return _ALIAS_CACHE["ai_llm"]


def closed_loop_module() -> Any:
    """Existing closed-loop module (pure ``plan_records`` is used here)."""
    if "closed_loop" not in _ALIAS_CACHE:
        _ALIAS_CACHE["closed_loop"] = _load_service_module(
            "cognify_core_app", _CORE_APP_DIR, "closed_loop"
        )
    return _ALIAS_CACHE["closed_loop"]


def core_service_module(module_name: str) -> Any:
    """Load another existing core-backend app module under the shared alias.

    Additive Step 14 helper: ``learner_engine``, ``repositories`` and ``db``
    resolve through the same alias mechanism (``cognify_core_app``), so no
    second import system is needed. Existing helpers are unchanged.
    """
    if not isinstance(module_name, str) or not module_name.strip():
        raise ValueError("module_name must be a non-empty string.")
    return _load_service_module(
        "cognify_core_app", _CORE_APP_DIR, module_name.strip()
    )


# ---------------------------------------------------------------------------
# Execution (reuses the existing sandbox + evaluator; no new mechanism)
# ---------------------------------------------------------------------------
def make_scripted_python_runner(
    script_by_stdin: dict[str, dict[str, Any]],
    *,
    default_stdout: str = "",
    default_stderr: str = "",
    default_exit_code: int = 0,
    default_timed_out: bool = False,
    default_time_ms: int = 5,
) -> Any:
    """Build a deterministic PythonRunner backed by the existing FakeSandbox.

    Args:
        script_by_stdin: stdin -> sandbox fields (stdout/stderr/exit_code/
            timed_out/time_ms). Each entry is programmed for the existing
            ``RUN_COMMAND`` (``python /workspace/solution.py``), exactly as
            the existing execution-service unit tests do.
    """
    if not isinstance(script_by_stdin, dict):
        raise TypeError(
            "script_by_stdin must be a dict, "
            f"got {type(script_by_stdin).__name__}."
        )
    mods = execution_modules()
    sandbox_mod = mods["sandbox"]
    runner_mod = mods["python_runner"]
    sandbox = sandbox_mod.FakeSandboxRunner(
        default=sandbox_mod.SandboxResult(
            stdout=default_stdout,
            stderr=default_stderr,
            exit_code=default_exit_code,
            timed_out=default_timed_out,
            time_ms=default_time_ms,
        )
    )
    run_command = list(runner_mod.RUN_COMMAND)
    for stdin_data, fields in script_by_stdin.items():
        if not isinstance(stdin_data, str):
            raise TypeError("script stdin keys must be str.")
        if not isinstance(fields, dict):
            raise TypeError("script values must be dicts of sandbox fields.")
        result = sandbox_mod.SandboxResult(
            stdout=str(fields.get("stdout", "")),
            stderr=str(fields.get("stderr", "")),
            exit_code=int(fields.get("exit_code", 0)),
            timed_out=bool(fields.get("timed_out", False)),
            time_ms=int(fields.get("time_ms", default_time_ms)),
        )
        sandbox.program(run_command, stdin_data, result)
    return runner_mod.PythonRunner(sandbox=sandbox)


def script_for_outputs(
    problem: Problem,
    handler: Any,
    *,
    time_ms: int = 5,
) -> dict[str, dict[str, Any]]:
    """Build a ``make_scripted_python_runner`` script from a handler.

    ``handler(stdin, expected_output)`` returns one of:
    - ``"correct"``: sandbox returns the expected output (pass);
    - ``str``: sandbox returns that string as stdout (compared verbatim);
    - ``dict``: full sandbox fields (for errors/timeouts).
    """
    if not isinstance(problem, Problem):
        raise TypeError(
            f"problem must be Problem, got {type(problem).__name__}."
        )
    script: dict[str, dict[str, Any]] = {}
    for case in problem.all_tests():
        outcome = handler(case.input, case.expected_output)
        if outcome == "correct":
            script[case.input] = {
                "stdout": case.expected_output + "\n",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "time_ms": time_ms,
            }
        elif isinstance(outcome, dict):
            merged = {"time_ms": time_ms}
            merged.update(outcome)
            script[case.input] = merged
        elif isinstance(outcome, str):
            script[case.input] = {
                "stdout": outcome,
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "time_ms": time_ms,
            }
        else:
            raise TypeError(
                "handler must return 'correct', str, or dict, "
                f"got {type(outcome).__name__}."
            )
    return script


def execute_problem(
    problem: Problem,
    code: str,
    runner: Any,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """Run student ``code`` against ALL of ``problem``'s tests (public+hidden).

    Uses the existing ``evaluator.evaluate`` with the given runner (which
    must be the existing PythonRunner for ``language == 'python'``). The
    returned object is the existing ExecutionResult (with ``to_dict()``).
    """
    if not isinstance(problem, Problem):
        raise TypeError(
            f"problem must be Problem, got {type(problem).__name__}."
        )
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string.")
    if runner is None or not hasattr(runner, "run_single"):
        raise TypeError("runner must be the existing PythonRunner.")
    if getattr(runner, "language", "python") != problem.language:
        raise ValueError(
            f"Runner language {getattr(runner, 'language', None)!r} does not "
            f"match problem language {problem.language!r}."
        )
    if isinstance(timeout_seconds, bool) or not isinstance(
        timeout_seconds, (int, float)
    ):
        raise ValueError("timeout_seconds must be a number.")
    if float(timeout_seconds) <= 0:
        raise ValueError("timeout_seconds must be positive.")
    evaluator = execution_modules()["evaluator"]
    return evaluator.evaluate(
        problem.language,
        code,
        list(problem.all_tests()),
        runner,
        timeout_seconds=float(timeout_seconds),
    )


def result_to_dict(result: Any) -> dict[str, Any]:
    """Deterministic dict form of an ExecutionResult (object or dict)."""
    if isinstance(result, dict):
        return copy.deepcopy(result)
    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(
        f"execution result must be a dict or ExecutionResult, "
        f"got {type(result).__name__}."
    )


def execution_status_str(result: Any) -> str:
    """Terminal status string (e.g. 'PASSED') for an execution result."""
    data = result_to_dict(result)
    raw = data.get("status", "")
    if not isinstance(raw, str):
        raw = getattr(raw, "value", raw)
    if not isinstance(raw, str):
        raise TypeError(
            f"ExecutionResult status must be str, got {type(raw).__name__}."
        )
    return raw.strip().upper()


# ---------------------------------------------------------------------------
# Student-facing view (hidden expected outputs are NEVER exposed here)
# ---------------------------------------------------------------------------
def to_student_view(problem: Problem, execution_result: Any) -> dict[str, Any]:
    """Redacted student-safe view: hidden ``expected_output`` removed.

    The full internal result (with hidden expectations) is what feeds the
    EvidencePack/diagnosis path; this view is what a student-facing API may
    return. Public tests keep their expectations; hidden tests get
    ``expected_output=None`` plus ``is_hidden=True``; the top-level
    ``expected_output`` is nulled when the decisive failure is hidden.
    """
    if not isinstance(problem, Problem):
        raise TypeError(
            f"problem must be Problem, got {type(problem).__name__}."
        )
    data = result_to_dict(execution_result)
    hidden_ids = {t.id for t in problem.hidden_tests}
    redacted_tests: list[dict[str, Any]] = []
    for entry in data.get("tests", []):
        item = dict(entry)
        item["is_hidden"] = item.get("test_id") in hidden_ids
        if item["is_hidden"]:
            item["expected_output"] = None
        redacted_tests.append(item)
    view = dict(data)
    view["tests"] = redacted_tests
    failed_id = view.get("failed_test_id")
    if failed_id in hidden_ids:
        view["expected_output"] = None
    view["problem_id"] = problem.problem_id
    view["language_track"] = problem.language
    view["hidden_redacted"] = True
    return copy.deepcopy(view)


# ---------------------------------------------------------------------------
# Evidence (reuses the existing Step 6 builder unchanged)
# ---------------------------------------------------------------------------
def default_learner_snapshot(
    problem: Problem,
    *,
    user_id: int = 1,
    journey_id: int = 1,
) -> LearnerSnapshot:
    """Minimal new-learner snapshot scoped to ``problem`` (no history)."""
    if not isinstance(problem, Problem):
        raise TypeError(
            f"problem must be Problem, got {type(problem).__name__}."
        )
    return LearnerSnapshot(
        user_id=user_id,
        journey_id=journey_id,
        language_track=problem.language,
        concept_state=ConceptStateSnapshot(concept_id=problem.concept_id),
    )


def build_pack_for_submission(
    code: str,
    problem: Problem,
    execution_result: Any,
    learner_snapshot: LearnerSnapshot | None = None,
) -> EvidencePack:
    """Build the Step 6 EvidencePack for one submission (thin wrapper)."""
    snapshot = (
        learner_snapshot
        if learner_snapshot is not None
        else default_learner_snapshot(problem)
    )
    return build_evidence_pack(
        code=code,
        problem=problem,
        execution_result=execution_result,
        learner_snapshot=snapshot,
    )


# ---------------------------------------------------------------------------
# Diagnosis (reuses the existing Step 7 service; fallback when no LLM)
# ---------------------------------------------------------------------------
def diagnose_evidence(pack: EvidencePack, client: Any = None) -> Any:
    """Diagnose one EvidencePack via the existing service (fallback default)."""
    service = ai_service_module()
    return service.diagnose_pack(pack, client)


def diagnose_via_http(
    pack: EvidencePack, client: Any = None
) -> tuple[int, dict[str, Any]]:
    """POST one pack through the existing /diagnose API (in-process client).

    Returns ``(status_code, body)``. With ``client=None`` the app resolves
    its LLM client from the environment (fallback-only in tests); pass the
    existing ``UnavailableLLMClient`` to force the fallback path.
    """
    from fastapi.testclient import TestClient

    main = ai_main_module()
    test_client = TestClient(main.create_app(llm_client=client))
    response = test_client.post("/diagnose", json={"evidence_pack": pack.to_dict()})
    try:
        body: dict[str, Any] = response.json()
    except ValueError:
        body = {"detail": response.text}
    return response.status_code, body


# ---------------------------------------------------------------------------
# Verification + closed-loop planning (honest: only actual execution results)
# ---------------------------------------------------------------------------
def verification_outcome_for(execution_status: Any) -> ExecutionOutcome:
    """Map an execution-service status to a verification ExecutionOutcome."""
    raw = execution_status
    if not isinstance(raw, str):
        raw = getattr(raw, "value", raw)
    if not isinstance(raw, str):
        raise TypeError(
            f"execution status must be str, got {type(raw).__name__}."
        )
    norm = raw.strip().upper()
    if norm not in EXECUTION_TO_VERIFICATION_OUTCOME:
        raise ValueError(
            f"Unknown execution status {execution_status!r}. Known: "
            f"{sorted(EXECUTION_TO_VERIFICATION_OUTCOME)}."
        )
    return normalize_execution_outcome(EXECUTION_TO_VERIFICATION_OUTCOME[norm])


def attempt_from_execution(
    problem: Problem,
    execution_result: Any,
    *,
    is_transfer: bool = False,
    misconception_id: str | None = None,
) -> VerificationAttempt:
    """Build a VerificationAttempt ONLY from an actual execution result."""
    if not isinstance(problem, Problem):
        raise TypeError(
            f"problem must be Problem, got {type(problem).__name__}."
        )
    if not isinstance(is_transfer, bool):
        raise TypeError(
            f"is_transfer must be bool, got {type(is_transfer).__name__}."
        )
    outcome = verification_outcome_for(execution_status_str(execution_result))
    return VerificationAttempt(
        problem_id=problem.problem_id,
        concept_id=problem.concept_id,
        language_track=problem.language,
        outcome=outcome,
        misconception_id=misconception_id,
        is_transfer=is_transfer if is_transfer else None,
        isomorphic_group_id=problem.isomorphic_group_id,
    )


def plan_records_for_context(context: Any) -> tuple[Any, ...]:
    """Pure closed-loop planning for a VerificationContext (no DB writes)."""
    return closed_loop_module().plan_records(context)


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "EXECUTION_TO_VERIFICATION_OUTCOME",
    "ai_llm_client_module",
    "ai_main_module",
    "ai_service_module",
    "attempt_from_execution",
    "build_pack_for_submission",
    "closed_loop_module",
    "core_service_module",
    "default_learner_snapshot",
    "diagnose_evidence",
    "diagnose_via_http",
    "execute_problem",
    "execution_modules",
    "execution_status_str",
    "make_scripted_python_runner",
    "plan_records_for_context",
    "result_to_dict",
    "script_for_outputs",
    "to_student_view",
    "verification_outcome_for",
]
