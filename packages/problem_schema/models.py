"""COGNIFY problem_schema — typed problem models.

Deterministic, framework-independent (stdlib only).
No DB, AI, execution, mastery, or adaptive logic here.
No code is executed; models only describe problems + test cases.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from packages.taxonomy import (
    SUPPORTED_LANGUAGES,
    is_valid_concept,
    is_valid_misconception,
    misconception_belongs_to,
)

VALID_VARIANT_ROLES: tuple[str, ...] = ("canonical", "transfer", "remedial")

DIFFICULTY_MIN: int = 1
DIFFICULTY_MAX: int = 5

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


def _require_id(value: object, field_name: str) -> str:
    text = _require_non_empty_str(value, field_name)
    if not _ID_RE.match(text):
        raise ValueError(
            f"{field_name} {value!r} is invalid. "
            "Use letters/digits plus '._-', starting with a letter/digit."
        )
    return text


def is_valid_variant_role(role: object) -> bool:
    """True iff `role` is canonical/transfer/remedial (case/space tolerant)."""
    if not isinstance(role, str):
        return False
    return role.strip().lower() in VALID_VARIANT_ROLES


def is_valid_difficulty(value: object) -> bool:
    """True iff `value` is an int in [1, 5] (bool rejected)."""
    return type(value) is int and DIFFICULTY_MIN <= value <= DIFFICULTY_MAX


def normalize_concept_id(concept_id: str) -> str:
    """Strip + upper-case; raises ValueError if unknown concept."""
    if not isinstance(concept_id, str):
        raise TypeError(f"concept_id must be str, got {type(concept_id).__name__}.")
    norm = concept_id.strip().upper()
    if not norm or not is_valid_concept(norm):
        raise ValueError(f"Unknown concept ID {concept_id!r}.")
    return norm


def normalize_language(language: str) -> str:
    """Strip + lower-case; raises ValueError if not python/java."""
    if not isinstance(language, str):
        raise TypeError(f"language must be str, got {type(language).__name__}.")
    norm = language.strip().lower()
    if norm not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unknown language {language!r}. Use one of {list(SUPPORTED_LANGUAGES)}."
        )
    return norm


def normalize_variant_role(role: str) -> str:
    """Strip + lower-case; raises ValueError if not a valid role."""
    if not isinstance(role, str):
        raise TypeError(f"variant_role must be str, got {type(role).__name__}.")
    norm = role.strip().lower()
    if norm not in VALID_VARIANT_ROLES:
        raise ValueError(
            f"Unknown variant_role {role!r}. Use one of {list(VALID_VARIANT_ROLES)}."
        )
    return norm


def normalize_misconception_ids(
    misconception_ids: object, concept_id: str
) -> tuple[str, ...]:
    """Validate + normalize misconception IDs for a (normalized) concept.

    Raises:
        TypeError: if not a list/tuple.
        ValueError: if empty, duplicated, unknown, or belonging to another concept.
    """
    if not isinstance(misconception_ids, (list, tuple)):
        raise TypeError(
            "misconception_ids must be a list/tuple of str, "
            f"got {type(misconception_ids).__name__}."
        )
    if len(misconception_ids) == 0:
        raise ValueError("misconception_ids must contain at least one ID.")
    normalized: list[str] = []
    for raw in misconception_ids:
        if not isinstance(raw, str):
            raise TypeError(
                f"misconception ID must be str, got {type(raw).__name__}."
            )
        norm = raw.strip().upper()
        if not norm or not is_valid_misconception(norm):
            raise ValueError(f"Unknown misconception ID {raw!r}.")
        if not misconception_belongs_to(norm, concept_id):
            raise ValueError(
                f"Misconception {norm!r} does not belong to concept {concept_id!r}."
            )
        normalized.append(norm)
    if len(set(normalized)) != len(normalized):
        raise ValueError(
            f"misconception_ids contains duplicates: {list(misconception_ids)!r}."
        )
    return tuple(normalized)


# ---------------------------------------------------------------------------
# TestCase
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TestCase:
    """One executable test: stdin `input` -> expected stdout/return.

    `id` is unique within its parent Problem (across public + hidden).
    `input` may be "" (no stdin). `expected_output` is the exact expected
    result (compared by the execution service, not here).
    """

    id: str
    input: str
    expected_output: str

    def __post_init__(self) -> None:
        norm_id = _require_id(self.id, "test id")
        if not isinstance(self.input, str):
            raise TypeError(
                f"test input must be str, got {type(self.input).__name__}."
            )
        if not isinstance(self.expected_output, str):
            raise TypeError(
                "test expected_output must be str, "
                f"got {type(self.expected_output).__name__}."
            )
        object.__setattr__(self, "id", norm_id)

    def to_dict(self) -> dict[str, str]:
        """Deterministic JSON-compatible mapping."""
        return {
            "id": self.id,
            "input": self.input,
            "expected_output": self.expected_output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestCase":
        if not isinstance(data, dict):
            raise TypeError(f"TestCase.from_dict needs a dict, got {type(data).__name__}.")
        try:
            tid = data["id"]
            tin = data["input"]
            tout = data["expected_output"]
        except KeyError as exc:
            raise ValueError(f"TestCase dict missing key: {exc}.") from exc
        return cls(id=tid, input=tin, expected_output=tout)


def _coerce_tests(value: object, field_name: str) -> tuple[TestCase, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"{field_name} must be a list/tuple of TestCase, "
            f"got {type(value).__name__}."
        )
    items = tuple(value)
    for item in items:
        if not isinstance(item, TestCase):
            raise TypeError(
                f"{field_name} entries must be TestCase, "
                f"got {type(item).__name__}."
            )
    return items


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Problem:
    """A single coding problem in the Cognify curriculum.

    Validation (in __post_init__):
      - concept_id: known taxonomy concept (case/space tolerant, stored UPPER)
      - language: python/java (case/space tolerant, stored lower)
      - difficulty: int 1..5 (bool rejected)
      - variant_role: canonical/transfer/remedial (stored lower)
      - misconception_ids: each known AND belonging to `concept_id`
      - public_tests: >= 1; hidden_tests: >= 0; test IDs unique across both
    """

    problem_id: str
    concept_id: str
    language: str
    difficulty: int
    title: str
    description: str
    constraints: tuple[str, ...] | list[str]
    starter_code: str
    input_format: str
    output_format: str
    public_tests: tuple[TestCase, ...] | list[TestCase]
    hidden_tests: tuple[TestCase, ...] | list[TestCase]
    isomorphic_group_id: str
    variant_role: str
    misconception_ids: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        # IDs (stored stripped).
        norm_problem_id = _require_id(self.problem_id, "problem_id")
        norm_iso = _require_id(self.isomorphic_group_id, "isomorphic_group_id")

        # Concept / language / role (normalized + validated).
        norm_concept = normalize_concept_id(self.concept_id)
        norm_lang = normalize_language(self.language)
        norm_role = normalize_variant_role(self.variant_role)

        # Difficulty: exact int, 1..5.
        if type(self.difficulty) is not int:
            raise TypeError(
                f"difficulty must be int in [1, 5], got {type(self.difficulty).__name__}."
            )
        if not (DIFFICULTY_MIN <= self.difficulty <= DIFFICULTY_MAX):
            raise ValueError(
                f"difficulty must be in [1, 5], got {self.difficulty!r}."
            )

        # Text fields (stored stripped, except starter_code kept verbatim).
        norm_title = _require_non_empty_str(self.title, "title")
        norm_desc = _require_non_empty_str(self.description, "description")
        if not isinstance(self.starter_code, str) or not self.starter_code.strip():
            raise (
                TypeError(f"starter_code must be str, got {type(self.starter_code).__name__}.")
                if not isinstance(self.starter_code, str)
                else ValueError("starter_code must be a non-empty string.")
            )
        norm_input_fmt = _require_non_empty_str(self.input_format, "input_format")
        norm_output_fmt = _require_non_empty_str(self.output_format, "output_format")

        # Constraints: list/tuple of non-empty str, >= 1.
        if not isinstance(self.constraints, (list, tuple)):
            raise TypeError(
                "constraints must be a list/tuple of str, "
                f"got {type(self.constraints).__name__}."
            )
        if len(tuple(self.constraints)) == 0:
            raise ValueError("constraints must contain at least one entry.")
        norm_constraints: list[str] = []
        for entry in self.constraints:  # type: ignore[union-attr]
            norm_constraints.append(_require_non_empty_str(entry, "constraint"))

        # Tests: coerce, check counts + duplicate IDs.
        public = _coerce_tests(self.public_tests, "public_tests")
        hidden = _coerce_tests(self.hidden_tests, "hidden_tests")
        if len(public) == 0:
            raise ValueError("public_tests must contain at least one TestCase.")
        seen: set[str] = set()
        for case in (*public, *hidden):
            if case.id in seen:
                raise ValueError(f"Duplicate test id {case.id!r} in problem.")
            seen.add(case.id)

        # Misconceptions: validated against the *normalized* concept.
        norm_misconceptions = normalize_misconception_ids(
            self.misconception_ids, norm_concept
        )

        # Store normalized values (frozen -> object.__setattr__).
        object.__setattr__(self, "problem_id", norm_problem_id)
        object.__setattr__(self, "concept_id", norm_concept)
        object.__setattr__(self, "language", norm_lang)
        object.__setattr__(self, "difficulty", self.difficulty)
        object.__setattr__(self, "title", norm_title)
        object.__setattr__(self, "description", norm_desc)
        object.__setattr__(self, "constraints", tuple(norm_constraints))
        object.__setattr__(self, "input_format", norm_input_fmt)
        object.__setattr__(self, "output_format", norm_output_fmt)
        object.__setattr__(self, "public_tests", public)
        object.__setattr__(self, "hidden_tests", hidden)
        object.__setattr__(self, "isomorphic_group_id", norm_iso)
        object.__setattr__(self, "variant_role", norm_role)
        object.__setattr__(self, "misconception_ids", norm_misconceptions)

    # -- convenience ------------------------------------------------------
    def all_tests(self) -> tuple[TestCase, ...]:
        """Public + hidden tests in stable order (public first)."""
        return (*self.public_tests, *self.hidden_tests)  # type: ignore[union-attr]

    def test_ids(self) -> tuple[str, ...]:
        """All test IDs (public first, then hidden)."""
        return tuple(t.id for t in self.all_tests())

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible mapping (lists, not tuples)."""
        return {
            "problem_id": self.problem_id,
            "concept_id": self.concept_id,
            "language": self.language,
            "difficulty": self.difficulty,
            "title": self.title,
            "description": self.description,
            "constraints": list(self.constraints),  # type: ignore[union-attr]
            "starter_code": self.starter_code,
            "input_format": self.input_format,
            "output_format": self.output_format,
            "public_tests": [t.to_dict() for t in self.public_tests],  # type: ignore[union-attr]
            "hidden_tests": [t.to_dict() for t in self.hidden_tests],  # type: ignore[union-attr]
            "isomorphic_group_id": self.isomorphic_group_id,
            "variant_role": self.variant_role,
            "misconception_ids": list(self.misconception_ids),  # type: ignore[union-attr]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Problem":
        if not isinstance(data, dict):
            raise TypeError(f"Problem.from_dict needs a dict, got {type(data).__name__}.")
        required = (
            "problem_id",
            "concept_id",
            "language",
            "difficulty",
            "title",
            "description",
            "constraints",
            "starter_code",
            "input_format",
            "output_format",
            "public_tests",
            "hidden_tests",
            "isomorphic_group_id",
            "variant_role",
            "misconception_ids",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"Problem dict missing keys: {missing}.")
        raw_public = data["public_tests"]
        raw_hidden = data["hidden_tests"]
        if not isinstance(raw_public, (list, tuple)):
            raise TypeError("public_tests must be a list of dicts.")
        if not isinstance(raw_hidden, (list, tuple)):
            raise TypeError("hidden_tests must be a list of dicts.")
        public = tuple(
            t if isinstance(t, TestCase) else TestCase.from_dict(t) for t in raw_public
        )
        hidden = tuple(
            t if isinstance(t, TestCase) else TestCase.from_dict(t) for t in raw_hidden
        )
        return cls(
            problem_id=data["problem_id"],
            concept_id=data["concept_id"],
            language=data["language"],
            difficulty=data["difficulty"],
            title=data["title"],
            description=data["description"],
            constraints=data["constraints"],
            starter_code=data["starter_code"],
            input_format=data["input_format"],
            output_format=data["output_format"],
            public_tests=public,
            hidden_tests=hidden,
            isomorphic_group_id=data["isomorphic_group_id"],
            variant_role=data["variant_role"],
            misconception_ids=data["misconception_ids"],
        )


__all__ = [
    "DIFFICULTY_MAX",
    "DIFFICULTY_MIN",
    "SUPPORTED_LANGUAGES",
    "VALID_VARIANT_ROLES",
    "Problem",
    "TestCase",
    "is_valid_difficulty",
    "is_valid_variant_role",
    "normalize_concept_id",
    "normalize_language",
    "normalize_misconception_ids",
    "normalize_variant_role",
]
