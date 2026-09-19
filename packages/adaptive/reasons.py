"""COGNIFY adaptive — reason templates (Step 9).

Pure string builders so every recommendation explains WHY it was ranked.
No DB, no LLM, no randomness. All messages are deterministic functions of
their inputs and always stay within the 10..500 char model bound.
"""
from __future__ import annotations


def prerequisite_reason(prereq_id: str, blocked_id: str, mastery: float, threshold: float) -> str:
    return (
        f"Prerequisite {prereq_id} mastery is {mastery:.2f}, below the required "
        f"{threshold:.2f}, so review {prereq_id} before advancing to {blocked_id}."
    )


def low_mastery_reason(concept_id: str, mastery: float) -> str:
    return (
        f"{concept_id} mastery is {mastery:.2f}, below 0.40: review the concept "
        f"and attempt targeted remedial practice."
    )


def recurring_reason(concept_id: str, misconception_id: str, recent: int, total: int) -> str:
    return (
        f"Recurring weakness {misconception_id} in {concept_id} "
        f"({recent} recent, {total} total): prioritize review and remedial "
        f"practice targeting {misconception_id}."
    )


def emerging_reason(concept_id: str, mastery: float) -> str:
    return (
        f"{concept_id} mastery is {mastery:.2f} (emerging): additional practice "
        f"is appropriate to consolidate the concept."
    )


def proficient_reason(concept_id: str, mastery: float) -> str:
    return (
        f"{concept_id} mastery is {mastery:.2f} (proficient): practice to "
        f"consolidate, with transfer when readiness evidence is sufficient."
    )


def transfer_ready_reason(concept_id: str, mastery: float, rate: float) -> str:
    return (
        f"{concept_id} mastery is {mastery:.2f} with transfer success "
        f"{rate:.2f}: attempt an isomorphic transfer variant to verify "
        f"generalization."
    )


def challenge_ready_reason(concept_id: str, mastery: float) -> str:
    return (
        f"{concept_id} mastery is {mastery:.2f} (mastered): attempt a "
        f"challenge problem to extend the concept."
    )


def declining_reason(concept_id: str, base: str) -> str:
    return f"{base} Trend is declining for {concept_id}, so review is urgent."


def hint_dependence_reason(concept_id: str, dependence: float) -> str:
    return (
        f"Hint dependence is {dependence:.2f} for {concept_id}: prefer concept "
        f"review or easier targeted practice over harder problems."
    )


__all__ = [
    "challenge_ready_reason",
    "declining_reason",
    "emerging_reason",
    "hint_dependence_reason",
    "low_mastery_reason",
    "prerequisite_reason",
    "proficient_reason",
    "recurring_reason",
    "transfer_ready_reason",
]
