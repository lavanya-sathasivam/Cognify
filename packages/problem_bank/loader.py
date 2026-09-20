"""COGNIFY problem_bank — deterministic problem loader (Steps 12 + 21A).

Loads ``problem-bank/<language>/*.json`` into the EXISTING
``packages.problem_schema.Problem`` model (single source of truth — no new
schema). Validation (problem ID, language, concept, difficulty, test
cases, isomorphic group, variant role, required fields) is owned entirely
by ``Problem.from_dict``; this module only handles deterministic file
discovery + JSON parsing with clear errors.

Language layout (Step 21A):
- ``problem-bank/python/*.json`` — Python problems (default bank dir).
- ``problem-bank/java/*.json`` — Java problems.
- Existing callers default to the Python-only bank (``DEFAULT_BANK_DIR``)
  for backward compatibility; the ``*_all`` helpers discover both
  languages explicitly.

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
DEFAULT_BANK_ROOT: Path = _REPO_ROOT / "problem-bank"

# Discovery order for the combined bank (deterministic: python first).
SUPPORTED_BANK_LANGUAGES: tuple[str, ...] = ("python", "java")


def _resolve_bank_dir(bank_dir: str | Path | None) -> Path:
    target = DEFAULT_BANK_DIR if bank_dir is None else Path(bank_dir)
    if not isinstance(target, Path):  # pragma: no cover - defensive
        raise TypeError(f"bank_dir must be a path, got {type(target).__name__}.")
    if not target.exists():
        raise ValueError(f"Problem bank directory does not exist: {target}.")
    if not target.is_dir():
        raise ValueError(f"Problem bank path is not a directory: {target}.")
    return target


def _resolve_bank_root(bank_root: str | Path | None) -> Path:
    target = DEFAULT_BANK_ROOT if bank_root is None else Path(bank_root)
    if not isinstance(target, Path):  # pragma: no cover - defensive
        raise TypeError(f"bank_root must be a path, got {type(target).__name__}.")
    if not target.exists():
        raise ValueError(f"Problem bank root does not exist: {target}.")
    if not target.is_dir():
        raise ValueError(f"Problem bank root is not a directory: {target}.")
    return target


def _language_dirs(bank_root: Path) -> list[Path]:
    """Existing ``<root>/<language>`` dirs in SUPPORTED_BANK_LANGUAGES order."""
    dirs: list[Path] = []
    for language in SUPPORTED_BANK_LANGUAGES:
        candidate = bank_root / language
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


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


def _iter_bank_files_all(bank_root: Path) -> list[Path]:
    """All ``*.json`` files across python+java dirs (deterministic order).

    Sorted by ``(language_dir_name, file_name)`` so repeated runs with
    the same files on disk yield equal results.
    """
    files: list[Path] = []
    for language_dir in _language_dirs(bank_root):
        files.extend(_iter_bank_files(language_dir))
    return sorted(files, key=lambda p: (p.parent.name, p.name))


def list_problem_ids(bank_dir: str | Path | None = None) -> list[str]:
    """Sorted problem IDs for every valid ``*.json`` in the bank dir.

    Backward-compatible default: the Python-only bank
    (``DEFAULT_BANK_DIR``). Use ``list_problem_ids_all`` for python+java.
    """
    resolved = _resolve_bank_dir(bank_dir)
    ids: list[str] = []
    for path in _iter_bank_files(resolved):
        ids.append(load_problem_file(path).problem_id)
    return sorted(ids)


def load_all_problems(
    bank_dir: str | Path | None = None,
) -> dict[str, Problem]:
    """All bank problems keyed by problem_id (deterministic key order).

    Backward-compatible default: the Python-only bank
    (``DEFAULT_BANK_DIR``). Use ``load_all_problems_all`` for python+java.
    """
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

    Backward-compatible default: searches the Python-only bank
    (``DEFAULT_BANK_DIR``). Pass an explicit ``bank_dir`` (e.g. the java
    dir) or use ``load_problem_all`` to reach Java problems.

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


# ---------------------------------------------------------------------------
# Multi-language discovery (Step 21A; explicit opt-in, default untouched)
# ---------------------------------------------------------------------------
def list_problem_ids_all(bank_root: str | Path | None = None) -> list[str]:
    """Sorted problem IDs across ``problem-bank/python`` + ``problem-bank/java``."""
    problems = load_all_problems_all(bank_root)
    return sorted(problems)


def load_all_problems_all(
    bank_root: str | Path | None = None,
) -> dict[str, Problem]:
    """All bank problems across python+java dirs, keyed by problem_id.

    Deterministic key order (sorted by problem_id). Duplicate problem IDs
    across language dirs raise ``ValueError`` naming both files.
    """
    resolved = _resolve_bank_root(bank_root)
    problems: dict[str, Problem] = {}
    seen_file: dict[str, Path] = {}
    for path in _iter_bank_files_all(resolved):
        problem = load_problem_file(path)
        if problem.problem_id in problems:
            raise ValueError(
                f"Duplicate problem_id {problem.problem_id!r} in bank "
                f"{resolved} (files {seen_file[problem.problem_id].name} "
                f"and {path.parent.name}/{path.name})."
            )
        problems[problem.problem_id] = problem
        seen_file[problem.problem_id] = path
    return dict(sorted(problems.items(), key=lambda kv: kv[0]))


def load_problem_all(
    problem_id: str, bank_root: str | Path | None = None
) -> Problem:
    """Load ONE problem by ID searching both python+java dirs.

    Raises:
        TypeError: ``problem_id`` is not a str.
        ValueError: empty ID, bank root missing, no match, or duplicates.
    """
    if not isinstance(problem_id, str):
        raise TypeError(
            f"problem_id must be str, got {type(problem_id).__name__}."
        )
    wanted = problem_id.strip()
    if not wanted:
        raise ValueError("problem_id must be a non-empty string.")
    problems = load_all_problems_all(bank_root)
    matches = [p for pid, p in problems.items() if pid == wanted]
    if not matches:
        resolved = _resolve_bank_root(bank_root)
        raise ValueError(
            f"Unknown problem_id {wanted!r} in bank {resolved}. "
            f"Known: {sorted(problems)}."
        )
    return matches[0]


__all__ = [
    "DEFAULT_BANK_DIR",
    "DEFAULT_BANK_ROOT",
    "SUPPORTED_BANK_LANGUAGES",
    "list_problem_ids",
    "list_problem_ids_all",
    "load_all_problems",
    "load_all_problems_all",
    "load_problem",
    "load_problem_all",
    "load_problem_file",
]
