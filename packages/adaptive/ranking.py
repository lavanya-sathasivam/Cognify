"""COGNIFY adaptive — deterministic ranking (Step 9).

Pure sort only. Policy (``policy.py``) assigns integer priorities;
this module orders candidates reproducibly with no randomness:

  key = (-priority, concept_id, action_type.value, problem_id or "",
         reason_code.value, reason)

Higher priority ranks first. All tie-breakers are lexicographic over
stable fields, so the same input always yields the same output list.
"""
from __future__ import annotations

from .models import Recommendation


def rank_key(rec: Recommendation) -> tuple:
    return (
        -rec.priority,
        rec.concept_id,
        rec.action_type.value,
        rec.problem_id or "",
        rec.reason_code.value,
        rec.reason,
    )


def rank_recommendations(
    recommendations: list[Recommendation] | tuple[Recommendation, ...],
) -> list[Recommendation]:
    """Return candidates in deterministic ranked order (new list)."""
    recs = list(recommendations)
    for item in recs:
        if not isinstance(item, Recommendation):
            raise TypeError(
                "recommendations entries must be Recommendation, "
                f"got {type(item).__name__}."
            )
    return sorted(recs, key=rank_key)


__all__ = ["rank_key", "rank_recommendations"]
