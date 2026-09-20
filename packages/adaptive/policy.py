"""COGNIFY adaptive — deterministic policy R1..R8 (Step 9).

Pure functions only. No DB, no LLM, no randomness, no mastery calculation
(Step 8 owns mastery; this module only READS supplied mastery values).

Rules (transparent heuristic):
  R1 PREREQUISITE GATE: prereq mastery < threshold -> REVIEW_PREREQUISITE
     (priority 100, always first); suppress CHALLENGE/TRANSFER downstream.
  R2 VERY LOW (mastery < 0.40) -> REVIEW_CONCEPT + REMEDIAL_PROBLEM.
  R3 RECURRING misconception -> REVIEW_CONCEPT / REMEDIAL targeting it
     (+15 priority, reason explicitly says "Recurring weakness").
  R4 EMERGING [0.40, 0.60) -> PRACTICE_PROBLEM.
  R5 PROFICIENT [0.60, 0.80) -> PRACTICE_PROBLEM + TRANSFER when ready.
  R6 MASTERED >= 0.80 -> CHALLENGE_PROBLEM (+ TRANSFER when ready),
     suppressed when recurring/declining/hint-high.
  R7 DECLINING trend -> +10 to REVIEW_CONCEPT / PRACTICE_PROBLEM.
  R8 HIGH hint dependence (>= 0.50) -> +10 to REVIEW_CONCEPT, suppress
     CHALLENGE/TRANSFER (never push difficulty upward when dependent).

Priority = base + urgency + boosts, where
urgency = round((1.0 - mastery) * 10) so weaker concepts rank first
within the same action type without crossing action tiers.
Ranking order itself lives in ``ranking.py``; this module only assigns
the integer priorities deterministically.
"""
from __future__ import annotations

from typing import Any

from . import reasons as reason_text
from .models import (
    ActionType,
    ConceptState,
    CurriculumInfo,
    MisconceptionState,
    ProblemInfo,
    ReasonCode,
    Recommendation,
)

DEFAULT_MASTERY_THRESHOLD: float = 0.60
HIGH_HINT_THRESHOLD: float = 0.50
TRANSFER_MIN_ATTEMPTS: int = 2

NOVICE_CEIL: float = 0.40
EMERGING_CEIL: float = 0.60
PROFICIENT_CEIL: float = 0.80

BASE_PRIORITY: dict[ActionType, int] = {
    ActionType.REVIEW_PREREQUISITE: 100,
    ActionType.REVIEW_CONCEPT: 80,
    ActionType.REMEDIAL_PROBLEM: 70,
    ActionType.PRACTICE_PROBLEM: 50,
    ActionType.TRANSFER_PROBLEM: 40,
    ActionType.CHALLENGE_PROBLEM: 30,
}

RECURRING_BOOST: int = 15
DECLINING_BOOST: int = 10
HINT_REVIEW_BOOST: int = 10


def urgency_bonus(mastery: float) -> int:
    """Weaker mastery -> larger bonus (0..10), deterministic."""
    return int(round((1.0 - float(mastery)) * 10))


def is_hint_high(state: ConceptState) -> bool:
    return float(state.hint_dependence) >= HIGH_HINT_THRESHOLD


def is_declining(state: ConceptState) -> bool:
    return state.trend == "declining"


def recurring_for_concept(
    misconceptions: list[MisconceptionState] | tuple[MisconceptionState, ...],
    concept_id: str,
) -> list[MisconceptionState]:
    """Recurring misconceptions for one concept, sorted by ID (deterministic)."""
    norm = concept_id.strip().upper()
    out = [m for m in misconceptions if m.concept_id == norm and m.is_recurring]
    return sorted(out, key=lambda m: m.misconception_id)


def is_transfer_ready(
    state: ConceptState, misconceptions: list[MisconceptionState]
) -> bool:
    """Enough evidence for a transfer variant (deterministic)."""
    if float(state.mastery) < NOVICE_CEIL + 0.20:  # >= 0.60
        return False
    if state.attempt_count < TRANSFER_MIN_ATTEMPTS:
        return False
    if is_hint_high(state):
        return False
    if is_declining(state):
        return False
    if any(m.is_recurring for m in misconceptions if m.concept_id == state.concept_id):
        return False
    return True


def is_challenge_ready(
    state: ConceptState, misconceptions: list[MisconceptionState]
) -> bool:
    """Whether a challenge problem is appropriate (deterministic)."""
    if float(state.mastery) < PROFICIENT_CEIL:
        return False
    if is_hint_high(state):
        return False
    if is_declining(state):
        return False
    if any(m.is_recurring for m in misconceptions if m.concept_id == state.concept_id):
        return False
    return True


def _select_problem(
    problems: list[ProblemInfo] | tuple[ProblemInfo, ...],
    concept_id: str,
    variant_role: str,
    hardest: bool = False,
) -> ProblemInfo | None:
    """Deterministically pick a problem for (concept, role) or None.

    Sort: easiest-first (difficulty asc, problem_id asc) except CHALLENGE
    which picks hardest-first (difficulty desc, problem_id asc).
    """
    norm = concept_id.strip().upper()
    role = variant_role.strip().lower()
    candidates = [p for p in problems if p.concept_id == norm and p.variant_role == role]
    if not candidates:
        return None
    if hardest:
        candidates = sorted(candidates, key=lambda p: (-p.difficulty, p.problem_id))
    else:
        candidates = sorted(candidates, key=lambda p: (p.difficulty, p.problem_id))
    return candidates[0]


def _fallback_problem(
    problems: list[ProblemInfo] | tuple[ProblemInfo, ...],
    concept_id: str,
) -> ProblemInfo | None:
    """Easiest canonical problem for a concept (deterministic fallback)."""
    return _select_problem(problems, concept_id, "canonical", hardest=False)


def _evidence_base(
    state: ConceptState,
    threshold: float,
    language_track: str | None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "concept_id": state.concept_id,
        "mastery": state.mastery,
        "mastery_band": state.mastery_band,
        "mastery_threshold": threshold,
        "trend": state.trend,
        "attempt_count": state.attempt_count,
        "pass_count": state.pass_count,
        "fail_count": state.fail_count,
        "recent_pass_rate": state.recent_pass_rate,
        "hint_dependence": state.hint_dependence,
        "transfer_success_rate": state.transfer_success_rate,
        "transfer_attempts": state.transfer_attempts,
        "transfer_successes": state.transfer_successes,
    }
    if language_track is not None:
        evidence["language_track"] = language_track
    elif state.language_track is not None:
        evidence["language_track"] = state.language_track
    return evidence


def evaluate_concept(
    state: ConceptState,
    misconceptions: list[MisconceptionState] | tuple[MisconceptionState, ...],
    curriculum: CurriculumInfo | None,
    problems: list[ProblemInfo] | tuple[ProblemInfo, ...],
    *,
    language_track: str | None = None,
    blocked: bool = False,
) -> list[Recommendation]:
    """Candidate actions for ONE concept (unsorted; priorities assigned).

    ``blocked`` is True when a prerequisite is unmet (R1): harder actions
    (CHALLENGE/TRANSFER) are suppressed for this concept.
    """
    misconceptions = list(misconceptions)
    problems = list(problems)
    threshold = curriculum.mastery_threshold if curriculum is not None else DEFAULT_MASTERY_THRESHOLD
    recs: list[Recommendation] = []
    urgency = urgency_bonus(state.mastery)
    declining = is_declining(state)
    hint_high = is_hint_high(state)
    recurring = [m for m in misconceptions if m.concept_id == state.concept_id and m.is_recurring]
    recurring = sorted(recurring, key=lambda m: m.misconception_id)
    primary_recurring = recurring[0] if recurring else None

    def _review_code() -> ReasonCode:
        if primary_recurring is not None:
            return ReasonCode.RECURRING_MISCONCEPTION
        if float(state.mastery) < NOVICE_CEIL:
            return ReasonCode.LOW_MASTERY
        if declining:
            return ReasonCode.DECLINING_TREND
        if hint_high:
            return ReasonCode.HIGH_HINT_DEPENDENCE
        return ReasonCode.LOW_MASTERY

    def _review_reason(code: ReasonCode) -> str:
        if code == ReasonCode.RECURRING_MISCONCEPTION and primary_recurring is not None:
            base = reason_text.recurring_reason(
                state.concept_id,
                primary_recurring.misconception_id,
                primary_recurring.recent_count,
                primary_recurring.occurrence_count,
            )
        elif code == ReasonCode.LOW_MASTERY:
            base = reason_text.low_mastery_reason(state.concept_id, float(state.mastery))
        elif code == ReasonCode.DECLINING_TREND:
            base = reason_text.declining_reason(
                state.concept_id,
                f"{state.concept_id} needs review.",
            )
        else:
            base = reason_text.hint_dependence_reason(
                state.concept_id, float(state.hint_dependence)
            )
        # Surface co-factors deterministically without changing the code.
        suffixes: list[str] = []
        if code != ReasonCode.RECURRING_MISCONCEPTION and primary_recurring is not None:
            suffixes.append(f"Recurring weakness {primary_recurring.misconception_id} is active.")
        if code != ReasonCode.DECLINING_TREND and declining:
            suffixes.append(f"Trend is declining for {state.concept_id}.")
        if code != ReasonCode.HIGH_HINT_DEPENDENCE and hint_high:
            suffixes.append(f"Hint dependence is {float(state.hint_dependence):.2f}.")
        text = base if not suffixes else base + " " + " ".join(suffixes)
        return text[:497] + "..." if len(text) > 500 else text

    def _review_evidence(code: ReasonCode) -> dict[str, Any]:
        ev = _evidence_base(state, threshold, language_track)
        if primary_recurring is not None:
            ev["misconception_id"] = primary_recurring.misconception_id
            ev["is_recurring"] = True
            ev["occurrence_count"] = primary_recurring.occurrence_count
            ev["recent_count"] = primary_recurring.recent_count
            ev["distinct_variant_count"] = primary_recurring.distinct_variant_count
        return ev

    def _review_priority() -> int:
        boost = 0
        if primary_recurring is not None:
            boost += RECURRING_BOOST
        if declining:
            boost += DECLINING_BOOST
        if hint_high:
            boost += HINT_REVIEW_BOOST
        return BASE_PRIORITY[ActionType.REVIEW_CONCEPT] + urgency + boost

    mastery = float(state.mastery)

    # -- R2 / R3 / R7 / R8: REVIEW_CONCEPT -------------------------------
    needs_review = (
        mastery < NOVICE_CEIL
        or primary_recurring is not None
        or declining
        or hint_high
    )
    if needs_review:
        code = _review_code()
        recs.append(
            Recommendation(
                action_type=ActionType.REVIEW_CONCEPT,
                concept_id=state.concept_id,
                priority=_review_priority(),
                reason_code=code,
                reason=_review_reason(code),
                supporting_evidence=_review_evidence(code),
                misconception_id=(
                    primary_recurring.misconception_id if primary_recurring else None
                ),
            )
        )

    # -- R2 / R3: REMEDIAL_PROBLEM ---------------------------------------
    needs_remedial = mastery < NOVICE_CEIL or primary_recurring is not None
    if needs_remedial:
        code = (
            ReasonCode.RECURRING_MISCONCEPTION
            if primary_recurring is not None
            else ReasonCode.LOW_MASTERY
        )
        if primary_recurring is not None:
            reason = reason_text.recurring_reason(
                state.concept_id,
                primary_recurring.misconception_id,
                primary_recurring.recent_count,
                primary_recurring.occurrence_count,
            )
        else:
            reason = reason_text.low_mastery_reason(state.concept_id, mastery)
        ev = _review_evidence(code)
        priority = BASE_PRIORITY[ActionType.REMEDIAL_PROBLEM] + urgency
        if primary_recurring is not None:
            priority += RECURRING_BOOST
        chosen = _select_problem(problems, state.concept_id, "remedial")
        if chosen is None:
            chosen = _fallback_problem(problems, state.concept_id)
        recs.append(
            Recommendation(
                action_type=ActionType.REMEDIAL_PROBLEM,
                concept_id=state.concept_id,
                priority=priority,
                reason_code=code,
                reason=reason[:497] + "..." if len(reason) > 500 else reason,
                supporting_evidence=ev,
                problem_id=chosen.problem_id if chosen else None,
                misconception_id=(
                    primary_recurring.misconception_id if primary_recurring else None
                ),
            )
        )

    # -- R4 / R5: PRACTICE_PROBLEM ----------------------------------------
    in_emerging = NOVICE_CEIL <= mastery < EMERGING_CEIL
    in_proficient = EMERGING_CEIL <= mastery < PROFICIENT_CEIL
    needs_practice = in_emerging or in_proficient
    if needs_practice:
        if declining:
            code = ReasonCode.DECLINING_TREND
            base = reason_text.declining_reason(
                state.concept_id,
                reason_text.proficient_reason(state.concept_id, mastery)
                if in_proficient
                else reason_text.emerging_reason(state.concept_id, mastery),
            )
        else:
            code = (
                ReasonCode.EMERGING_PRACTICE if in_emerging
                else ReasonCode.PROFICIENT_PRACTICE
            )
            base = (
                reason_text.emerging_reason(state.concept_id, mastery)
                if in_emerging
                else reason_text.proficient_reason(state.concept_id, mastery)
            )
        priority = BASE_PRIORITY[ActionType.PRACTICE_PROBLEM] + urgency
        if declining:
            priority += DECLINING_BOOST
        ev = _evidence_base(state, threshold, language_track)
        if primary_recurring is not None:
            ev["misconception_id"] = primary_recurring.misconception_id
            ev["is_recurring"] = True
        chosen = _select_problem(problems, state.concept_id, "canonical")
        if chosen is None:
            chosen = _fallback_problem(problems, state.concept_id)
        recs.append(
            Recommendation(
                action_type=ActionType.PRACTICE_PROBLEM,
                concept_id=state.concept_id,
                priority=priority,
                reason_code=code,
                reason=base[:497] + "..." if len(base) > 500 else base,
                supporting_evidence=ev,
                problem_id=chosen.problem_id if chosen else None,
            )
        )

    # -- R5 / R6: TRANSFER_PROBLEM -----------------------------------------
    wants_transfer = (in_proficient or mastery >= PROFICIENT_CEIL) and not blocked and not hint_high
    if wants_transfer and is_transfer_ready(state, misconceptions):
        reason = reason_text.transfer_ready_reason(
            state.concept_id, mastery, float(state.transfer_success_rate)
        )
        ev = _evidence_base(state, threshold, language_track)
        chosen = _select_problem(problems, state.concept_id, "transfer")
        recs.append(
            Recommendation(
                action_type=ActionType.TRANSFER_PROBLEM,
                concept_id=state.concept_id,
                priority=BASE_PRIORITY[ActionType.TRANSFER_PROBLEM] + urgency,
                reason_code=ReasonCode.READY_FOR_TRANSFER,
                reason=reason,
                supporting_evidence=ev,
                problem_id=chosen.problem_id if chosen else None,
            )
        )

    # -- R6: CHALLENGE_PROBLEM ----------------------------------------------
    if mastery >= PROFICIENT_CEIL and not blocked and is_challenge_ready(state, misconceptions):
        reason = reason_text.challenge_ready_reason(state.concept_id, mastery)
        ev = _evidence_base(state, threshold, language_track)
        chosen = _select_problem(problems, state.concept_id, "canonical", hardest=True)
        # Prefer a hard problem (difficulty >= 4) when catalog allows.
        if chosen is not None and chosen.difficulty < 4:
            harder = sorted(
                [p for p in problems if p.concept_id == state.concept_id],
                key=lambda p: (-p.difficulty, p.problem_id),
            )
            if harder and harder[0].difficulty >= 4:
                chosen = harder[0]
        recs.append(
            Recommendation(
                action_type=ActionType.CHALLENGE_PROBLEM,
                concept_id=state.concept_id,
                priority=BASE_PRIORITY[ActionType.CHALLENGE_PROBLEM] + urgency,
                reason_code=ReasonCode.READY_FOR_CHALLENGE,
                reason=reason,
                supporting_evidence=ev,
                problem_id=chosen.problem_id if chosen else None,
            )
        )

    return recs


def evaluate_all(
    states: list[ConceptState] | tuple[ConceptState, ...],
    misconceptions: list[MisconceptionState] | tuple[MisconceptionState, ...],
    curricula: list[CurriculumInfo] | tuple[CurriculumInfo, ...],
    problems: list[ProblemInfo] | tuple[ProblemInfo, ...],
    *,
    language_track: str | None = None,
) -> list[Recommendation]:
    """Evaluate R1..R8 across all supplied concepts (unsorted candidates).

    Pure: no sorting across concepts here (see ``ranking.py``). Prereq
    duplicates are merged deterministically (highest priority wins;
    ``blocked_for`` lists all blocked downstream concepts sorted).
    """
    states = list(states)
    misconceptions = list(misconceptions)
    curricula = list(curricula)
    problems = list(problems)

    track: str | None = None
    if language_track is not None:
        if not isinstance(language_track, str):
            raise TypeError(
                f"language_track must be str or None, got {type(language_track).__name__}."
            )
        from packages.taxonomy import SUPPORTED_LANGUAGES

        norm_track = language_track.strip().lower()
        if norm_track not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unknown language_track {language_track!r}.")
        track = norm_track
        for st in states:
            if st.language_track is not None and st.language_track != track:
                raise ValueError(
                    f"Concept {st.concept_id!r} track {st.language_track!r} does not "
                    f"match request track {track!r} (tracks must not cross)."
                )

    by_concept: dict[str, ConceptState] = {s.concept_id: s for s in states}
    if len(by_concept) != len(states):
        raise ValueError("Duplicate concept states for the same concept_id.")
    curriculum_by_concept: dict[str, CurriculumInfo] = {c.concept_id: c for c in curricula}

    # -- R1: prerequisite gate -------------------------------------------
    candidates: list[Recommendation] = []
    blocked_concepts: set[str] = set()
    prereq_actions: dict[str, Recommendation] = {}
    for state in sorted(states, key=lambda s: s.concept_id):
        curriculum = curriculum_by_concept.get(state.concept_id)
        prereqs = curriculum.prerequisites if curriculum is not None else ()
        for prereq_id in sorted(prereqs):
            prereq_state = by_concept.get(prereq_id)
            if prereq_state is None:
                continue  # insufficient data: never invent a violation
            prereq_curriculum = curriculum_by_concept.get(prereq_id)
            threshold = (
                prereq_curriculum.mastery_threshold
                if prereq_curriculum is not None
                else DEFAULT_MASTERY_THRESHOLD
            )
            if float(prereq_state.mastery) < threshold:
                blocked_concepts.add(state.concept_id)
                urgency = urgency_bonus(float(prereq_state.mastery))
                priority = BASE_PRIORITY[ActionType.REVIEW_PREREQUISITE] + urgency
                evidence: dict[str, Any] = {
                    "concept_id": prereq_id,
                    "blocked_concept_id": state.concept_id,
                    "mastery": prereq_state.mastery,
                    "mastery_threshold": threshold,
                    "trend": prereq_state.trend,
                    "attempt_count": prereq_state.attempt_count,
                }
                if track is not None:
                    evidence["language_track"] = track
                elif prereq_state.language_track is not None:
                    evidence["language_track"] = prereq_state.language_track
                reason = reason_text.prerequisite_reason(
                    prereq_id, state.concept_id, float(prereq_state.mastery), threshold
                )
                action = Recommendation(
                    action_type=ActionType.REVIEW_PREREQUISITE,
                    concept_id=prereq_id,
                    priority=priority,
                    reason_code=ReasonCode.PREREQUISITE_NOT_MASTERED,
                    reason=reason,
                    supporting_evidence=evidence,
                )
                # Merge duplicates: same prereq blocking several downstream.
                existing = prereq_actions.get(prereq_id)
                if existing is None or action.priority > existing.priority:
                    prereq_actions[prereq_id] = action
                elif action.priority == existing.priority:
                    merged_blocked = sorted(
                        set(
                            str(
                                existing.supporting_evidence.get(
                                    "blocked_concept_id", ""
                                )
                            )
                            + ","
                            + state.concept_id
                        ).difference({""})
                    )
                    _ = merged_blocked  # keep deterministic shape; reason stays canonical
    candidates.extend(sorted(prereq_actions.values(), key=lambda r: r.concept_id))

    # -- R2..R8 per concept --------------------------------------------------
    for state in sorted(states, key=lambda s: s.concept_id):
        curriculum = curriculum_by_concept.get(state.concept_id)
        concept_misconceptions = [m for m in misconceptions if m.concept_id == state.concept_id]
        candidates.extend(
            evaluate_concept(
                state,
                concept_misconceptions,
                curriculum,
                problems,
                language_track=track,
                blocked=(state.concept_id in blocked_concepts),
            )
        )
    return candidates


__all__ = [
    "BASE_PRIORITY",
    "DEFAULT_MASTERY_THRESHOLD",
    "DECLINING_BOOST",
    "EMERGING_CEIL",
    "HIGH_HINT_THRESHOLD",
    "HINT_REVIEW_BOOST",
    "NOVICE_CEIL",
    "PROFICIENT_CEIL",
    "RECURRING_BOOST",
    "TRANSFER_MIN_ATTEMPTS",
    "evaluate_all",
    "evaluate_concept",
    "is_challenge_ready",
    "is_transfer_ready",
    "urgency_bonus",
]
