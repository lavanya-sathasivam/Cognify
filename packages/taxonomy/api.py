"""COGNIFY taxonomy — query/validation helpers.

All helpers are pure, deterministic, and stdlib-only.
IDs are normalized with ``strip().upper()`` so ``" c1 "`` / ``"c1-m01"``
resolve to ``"C1"`` / ``"C1-M01"``.
"""
from __future__ import annotations

from .concepts import CONCEPTS, _CONCEPT_BY_ID, Concept
from .errors import (
    SUPPORTED_LANGUAGES,
    CrossCuttingError,
    Misconception,
    _CROSS_CUTTING_BY_ID,
    _MISCONCEPTION_BY_ID,
    CROSS_CUTTING_ERRORS,
    MISCONCEPTIONS_BY_CONCEPT,
)


def _normalize(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip().upper()
    return text or None


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------
def list_concepts() -> list[Concept]:
    """All 8 concepts in curriculum order C1..C8."""
    return list(CONCEPTS)


def list_concept_ids() -> list[str]:
    """Concept IDs in curriculum order, e.g. ["C1", ..., "C8"]."""
    return [c.id for c in CONCEPTS]


def is_valid_concept(concept_id: object) -> bool:
    """True iff `concept_id` names a known concept (case/space tolerant)."""
    norm = _normalize(concept_id)
    return norm in _CONCEPT_BY_ID if norm else False


def get_concept(concept_id: str) -> Concept:
    """Return the Concept for `concept_id`.

    Raises:
        KeyError: if unknown. Message lists valid IDs.
    """
    norm = _normalize(concept_id)
    if norm is None or norm not in _CONCEPT_BY_ID:
        raise KeyError(
            f"Unknown concept ID {concept_id!r}. Valid IDs: {list_concept_ids()}"
        )
    return _CONCEPT_BY_ID[norm]


# ---------------------------------------------------------------------------
# Misconceptions (per-concept)
# ---------------------------------------------------------------------------
def list_misconceptions(
    concept_id: str, language: str | None = None
) -> list[Misconception]:
    """Misconceptions for a concept, optionally filtered by language.

    Args:
        concept_id: e.g. "C1" (case/space tolerant).
        language: None (all), or "python" / "java" (case/space tolerant).

    Raises:
        KeyError: unknown concept ID.
        ValueError: unknown language filter.
    """
    concept = get_concept(concept_id)  # validates + normalizes
    items = list(MISCONCEPTIONS_BY_CONCEPT[concept.id])
    if language is None:
        return items
    if not isinstance(language, str):
        raise ValueError(
            f"Unknown language {language!r}. Use one of {list(SUPPORTED_LANGUAGES)} or None."
        )
    lang = language.strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unknown language {language!r}. Use one of {list(SUPPORTED_LANGUAGES)} or None."
        )
    return [m for m in items if lang in m.languages]


def is_valid_misconception(misconception_id: object) -> bool:
    """True iff `misconception_id` names a known per-concept misconception."""
    norm = _normalize(misconception_id)
    return norm in _MISCONCEPTION_BY_ID if norm else False


def get_misconception(misconception_id: str) -> Misconception:
    """Return the Misconception for `misconception_id` (e.g. "C2-M01").

    Raises:
        KeyError: if unknown.
    """
    norm = _normalize(misconception_id)
    if norm is None or norm not in _MISCONCEPTION_BY_ID:
        raise KeyError(
            f"Unknown misconception ID {misconception_id!r}."
        )
    return _MISCONCEPTION_BY_ID[norm]


def get_concept_for_misconception(misconception_id: str) -> Concept:
    """Return the parent Concept of a misconception ID."""
    return get_concept(get_misconception(misconception_id).concept_id)


def misconception_belongs_to(misconception_id: object, concept_id: object) -> bool:
    """True iff the misconception exists and belongs to the given concept."""
    m_norm = _normalize(misconception_id)
    c_norm = _normalize(concept_id)
    if m_norm is None or c_norm is None:
        return False
    m = _MISCONCEPTION_BY_ID.get(m_norm)
    return m is not None and m.concept_id == c_norm


# ---------------------------------------------------------------------------
# Cross-cutting errors
# ---------------------------------------------------------------------------
def list_cross_cutting_errors() -> list[CrossCuttingError]:
    """All 5 outcome-level errors in stable order."""
    return list(CROSS_CUTTING_ERRORS)


def list_cross_cutting_ids() -> list[str]:
    """Cross-cutting IDs, e.g. ["X-SYNTAX", ...]."""
    return [e.id for e in CROSS_CUTTING_ERRORS]


def is_valid_cross_cutting_error(error_id: object) -> bool:
    """True iff `error_id` names a known cross-cutting error."""
    norm = _normalize(error_id)
    return norm in _CROSS_CUTTING_BY_ID if norm else False


def get_cross_cutting_error(error_id: str) -> CrossCuttingError:
    """Return the CrossCuttingError for `error_id` (e.g. "X-TIMEOUT").

    Raises:
        KeyError: if unknown.
    """
    norm = _normalize(error_id)
    if norm is None or norm not in _CROSS_CUTTING_BY_ID:
        raise KeyError(
            f"Unknown cross-cutting error ID {error_id!r}. "
            f"Valid IDs: {list_cross_cutting_ids()}"
        )
    return _CROSS_CUTTING_BY_ID[norm]
