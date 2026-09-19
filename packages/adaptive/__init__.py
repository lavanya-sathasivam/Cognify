"""COGNIFY adaptive package (Step 9: Adaptive Engine / Roadmap Ranking).

Deterministic, stdlib-only pure policy: learner state + curriculum/problem
metadata -> ranked next-actions. No DB, no LLM, no randomness, no mastery
calculation (Step 8 owns mastery), no hints, no verification, no frontend.

Flow::

    Learner Model (Step 8 views)
      -> packages.adaptive.recommend_next_actions (pure)
      -> ranked Recommendation list

Typical thin integration (no DB writes)::

    from packages.adaptive import (
        ConceptState, MisconceptionState, CurriculumInfo, ProblemInfo,
        recommend_next_actions,
    )
    states = [ConceptState.from_learner_view(view_c5)]
    miscs = [MisconceptionState.from_misconception_view(view_m02)]
    curricula = [CurriculumInfo.from_taxonomy("C5")]
    problems = [ProblemInfo.from_dict({...}), ...]
    ranked = recommend_next_actions(states, miscs, curricula, problems)
"""
from __future__ import annotations

from typing import Any

from .models import (
    VALID_BANDS,
    VALID_TRENDS,
    VALID_VARIANT_ROLES,
    ActionType,
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    ProblemInfo,
    ReasonCode,
    Recommendation,
)
from .policy import (
    DEFAULT_MASTERY_THRESHOLD,
    HIGH_HINT_THRESHOLD,
    TRANSFER_MIN_ATTEMPTS,
    evaluate_all,
    evaluate_concept,
)
from .ranking import rank_key, rank_recommendations


def recommend_next_actions(
    states: list[ConceptState] | tuple[ConceptState, ...],
    misconceptions: list[MisconceptionState] | tuple[MisconceptionState, ...] = (),
    curricula: list[CurriculumInfo] | tuple[CurriculumInfo, ...] = (),
    problems: list[ProblemInfo] | tuple[ProblemInfo, ...] = (),
    *,
    language_track: str | None = None,
) -> list[Recommendation]:
    """Ranked next-actions for the supplied learner slice (pure).

    Args:
        states: one ConceptState per concept of interest.
        misconceptions: active misconception snapshots (may be empty).
        curricula: curriculum metadata; missing entries use taxonomy
            prerequisites with the default threshold (0.60).
        problems: problem catalog metadata; missing entries yield actions
            with ``problem_id=None`` (conceptual recommendation only).
        language_track: optional track scope (``python``/``java``). When set,
            every state carrying a track must match it (tracks must not
            cross); the track is echoed into supporting evidence.

    Returns:
        Ranked list (highest priority first), deterministic for equal inputs.
    """
    # Fill missing curricula from taxonomy so prerequisites are never silently
    # dropped when callers pass only states + problems.
    states = list(states)
    misconceptions = list(misconceptions)
    curricula = list(curricula)
    problems = list(problems)
    have = {c.concept_id for c in curricula}
    filled: list[CurriculumInfo] = list(curricula)
    for st in states:
        if st.concept_id not in have:
            filled.append(CurriculumInfo.from_taxonomy(st.concept_id))
    candidates = evaluate_all(states, misconceptions, filled, problems, language_track=language_track)
    return rank_recommendations(candidates)


def explain_recommendations(recommendations: list[Recommendation] | tuple[Recommendation, ...]) -> list[dict[str, Any]]:
    """JSON-able rendering answering 'Why am I seeing this problem?'."""
    out: list[dict[str, Any]] = []
    for rec in recommendations:
        if not isinstance(rec, Recommendation):
            raise TypeError(
                f"entries must be Recommendation, got {type(rec).__name__}."
            )
        out.append(rec.to_dict())
    return out


__all__ = [
    "DEFAULT_MASTERY_THRESHOLD",
    "HIGH_HINT_THRESHOLD",
    "TRANSFER_MIN_ATTEMPTS",
    "VALID_BANDS",
    "VALID_TRENDS",
    "VALID_VARIANT_ROLES",
    "ActionType",
    "ConceptState",
    "CurriculumInfo",
    "MisconceptionState",
    "ProblemInfo",
    "ReasonCode",
    "Recommendation",
    "evaluate_all",
    "evaluate_concept",
    "explain_recommendations",
    "rank_key",
    "rank_recommendations",
    "recommend_next_actions",
]
