"""COGNIFY problem_bank — deterministic problem loader (Step 12).

Loads ``problem-bank/python/*.json`` into the EXISTING
``packages.problem_schema.Problem`` model (single source of truth — no new
schema). Validation (problem ID, language, concept, difficulty, test
cases, isomorphic group, variant role, required fields) is owned entirely
by ``Problem.from_dict``; this module only handles deterministic file
discovery + JSON parsing with clear errors.

Determinism contract:
- Pure function of the files on disk: same files always yield equal
  Problems. Directory scans are sorted; JSON keys are not reordered.
- No clock, no randomness, no UUIDs, no I/O beyond reading the given
  files, no environment reads, no DB, no LLM.

Invalid problems fail clearly (ValueError/TypeError naming the file and
the underlying schema complaint).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.problem_schema.models import Problem

# .../packages/problem_bank/loader.py -> parents[2] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK_DIR: Path = _REPO_ROOT / "problem-bank" / "python"


def _resolve_bank_dir(bank_dir: str | Path | None) -> Path:
    target = DEFAULT_BANK_DIR if bank_dir is None else Path(bank_dir)
    if not isinstance(target, Path):  # pragma: no cover - defensive
        raise TypeError(f"bank_dir must be a path, got {type(target).__name__}.")
    if not target.exists():
        raise ValueError(f"Problem bank directory does not exist: {target}.")
    if not target.is_dir():
        raise ValueError(f"Problem bank path is not a directory: {target}.")
    return target


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read problem file {path}: {exc}.") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Problem file {path} is not valid JSON: {exc}."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"Problem file {path} must hold a JSON object, "
            f"got {type(data).__name__}."
        )
    return data


def load_problem_file(path: str | Path) -> Problem:
    """Load and validate ONE problem JSON file.

    Raises:
        ValueError: file missing, unreadable, invalid JSON, non-object,
            or failing ``Problem`` schema validation (message includes the
            file path plus the underlying complaint).
        TypeError: ``path`` is not a str/Path.
    """
    if not isinstance(path, (str, Path)):
        raise TypeError(f"path must be str or Path, got {type(path).__name__}.")
    target = Path(path)
    if not target.exists():
        raise ValueError(f"Problem file does not exist: {target}.")
    if not target.is_file():
        raise ValueError(f"Problem path is not a file: {target}.")
    data = _read_json_object(target)
    try:
        return Problem.from_dict(data)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid problem in {target}: {exc}.") from exc


def _iter_bank_files(bank_dir: Path) -> list[Path]:
    return sorted(
        (p for p in bank_dir.glob("*.json") if p.is_file()),
        key=lambda p: p.name,
    )


def list_problem_ids(bank_dir: str | Path | None = None) -> list[str]:
    """Sorted problem IDs for every valid ``*.json`` in the bank dir."""
    resolved = _resolve_bank_dir(bank_dir)
    ids: list[str] = []
    for path in _iter_bank_files(resolved):
        ids.append(load_problem_file(path).problem_id)
    return sorted(ids)


def load_all_problems(
    bank_dir: str | Path | None = None,
) -> dict[str, Problem]:
    """All bank problems keyed by problem_id (deterministic key order)."""
    resolved = _resolve_bank_dir(bank_dir)
    problems: dict[str, Problem] = {}
    for path in _iter_bank_files(resolved):
        problem = load_problem_file(path)
        if problem.problem_id in problems:
            raise ValueError(
                f"Duplicate problem_id {problem.problem_id!r} in bank "
                f"{resolved} (file {path.name})."
            )
        problems[problem.problem_id] = problem
    return dict(sorted(problems.items(), key=lambda kv: kv[0]))


def load_problem(
    problem_id: str, bank_dir: str | Path | None = None
) -> Problem:
    """Load ONE problem by ID from the bank directory.

    Raises:
        TypeError: ``problem_id`` is not a str.
        ValueError: empty ID, bank dir missing, no match, or duplicates.
    """
    if not isinstance(problem_id, str):
        raise TypeError(
            f"problem_id must be str, got {type(problem_id).__name__}."
        )
    wanted = problem_id.strip()
    if not wanted:
        raise ValueError("problem_id must be a non-empty string.")
    problems = load_all_problems(bank_dir)
    matches = [p for pid, p in problems.items() if pid == wanted]
    if not matches:
        resolved = _resolve_bank_dir(bank_dir)
        raise ValueError(
            f"Unknown problem_id {wanted!r} in bank {resolved}. "
            f"Known: {sorted(problems)}."
        )
    return matches[0]


__all__ = [
    "DEFAULT_BANK_DIR",
    "list_problem_ids",
    "load_all_problems",
    "load_problem",
    "load_problem_file",
]
