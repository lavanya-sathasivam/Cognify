"""COGNIFY mastery — recurring-weakness + improvement rules (Step 8).

Pure, deterministic predicates over plain data (no DB, no clock, no LLM).

Recurring weakness (any ONE fires):
  R1: same misconception >= RECENT_THRESHOLD (2) times in the last
      RECENT_WINDOW (5) relevant attempts.
  R2: same misconception >= HISTORICAL_THRESHOLD (3) times historically
      for the concept.
  R3: same misconception appears across >= VARIANT_THRESHOLD (2)
      isomorphic problem variants, i.e. >= 2 distinct problem_ids sharing
      one isomorphic_group_id (max distinct problem count within any single
      group). Counting bare distinct problem_ids is NOT sufficient: two
      unrelated problems from different groups must not fire R3.

Improvement:
  The misconception is improving/resolved when the next
  IMPROVEMENT_WINDOW (3) relevant attempts after its last occurrence are
  all passes and none of them re-contains the misconception. In the engine
  this is evaluated on the trailing window: the last 3 relevant attempts
  (including the current one) are all passes and the target ID appears in
  none of them.
"""
from __future__ import annotations

RECENT_WINDOW: int = 5
RECENT_THRESHOLD: int = 2
HISTORICAL_THRESHOLD: int = 3
VARIANT_THRESHOLD: int = 2
IMPROVEMENT_WINDOW: int = 3


def _require_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}.")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value!r}.")
    return value


def _normalize_mid(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"misconception_id must be str, got {type(value).__name__}."
        )
    text = value.strip().upper()
    if not text:
        raise ValueError("misconception_id must be a non-empty string.")
    return text


def check_recurring(
    occurrence_count: int,
    recent_count: int,
    distinct_variant_count: int,
) -> tuple[bool, str]:
    """Apply rules R1/R2/R3 deterministically.

    Args:
        occurrence_count: total historical occurrences (R2).
        recent_count: occurrences in the trailing RECENT_WINDOW (R1).
        distinct_variant_count: isomorphic-variant count for R3, i.e. the
            value of :func:`isomorphic_variant_count` (max distinct
            problem_ids within any single isomorphic_group_id). Callers must
            NOT pass a bare distinct-problem_id count.

    Returns ``(is_recurring, reason)``. ``reason`` names the first firing
    rule in R1 -> R2 -> R3 order, or a stable negative reason.
    """
    total = _require_non_negative_int(occurrence_count, "occurrence_count")
    recent = _require_non_negative_int(recent_count, "recent_count")
    variants = _require_non_negative_int(
        distinct_variant_count, "distinct_variant_count"
    )
    if recent >= RECENT_THRESHOLD:
        return True, (
            f"recurring: {recent} occurrence(s) in the last {RECENT_WINDOW} "
            f"attempts (>= {RECENT_THRESHOLD})"
        )
    if total >= HISTORICAL_THRESHOLD:
        return True, (
            f"recurring: {total} historical occurrence(s) "
            f"(>= {HISTORICAL_THRESHOLD})"
        )
    if variants >= VARIANT_THRESHOLD:
        return True, (
            f"recurring: seen across {variants} isomorphic problem variant(s) "
            f"(>= {VARIANT_THRESHOLD})"
        )
    return False, (
        f"not recurring: recent {recent}<{RECENT_THRESHOLD}, historical "
        f"{total}<{HISTORICAL_THRESHOLD}, variants {variants}<{VARIANT_THRESHOLD}"
    )


def recent_occurrence_count(
    attempt_misconceptions: list[str | None] | tuple[str | None, ...],
    target_id: str,
    window: int = RECENT_WINDOW,
) -> int:
    """Count ``target_id`` in the trailing ``window`` of attempt history.

    ``attempt_misconceptions`` is oldest -> newest; each entry is the
    diagnosed misconception for that attempt (or None for clean passes).
    Comparison is case/space tolerant.
    """
    if type(window) is not int or window < 1:
        raise ValueError(f"window must be a positive int, got {window!r}.")
    if not isinstance(attempt_misconceptions, (list, tuple)):
        raise TypeError(
            "attempt_misconceptions must be a list/tuple, "
            f"got {type(attempt_misconceptions).__name__}."
        )
    target = _normalize_mid(target_id)
    tail = list(attempt_misconceptions[-window:])
    count = 0
    for entry in tail:
        if entry is None:
            continue
        if not isinstance(entry, str):
            raise TypeError(
                "attempt_misconceptions entries must be str or None, "
                f"got {type(entry).__name__}."
            )
        if entry.strip().upper() == target:
            count += 1
    return count


def distinct_variant_count(variant_ids: list[str] | tuple[str, ...]) -> int:
    """Count distinct non-empty problem IDs (deterministic).

    Legacy helper kept for backward compatibility. It does NOT establish
    isomorphic identity on its own: two unrelated problems from different
    isomorphic groups also count as distinct here. R3 callers must use
    :func:`isomorphic_variant_count` instead.
    """
    if not isinstance(variant_ids, (list, tuple)):
        raise TypeError(
            f"variant_ids must be a list/tuple, got {type(variant_ids).__name__}."
        )
    seen: set[str] = set()
    for raw in variant_ids:
        if not isinstance(raw, str):
            raise TypeError(
                f"variant_ids entries must be str, got {type(raw).__name__}."
            )
        text = raw.strip()
        if text:
            seen.add(text)
    return len(seen)


def isomorphic_variant_count(
    occurrences: list[tuple[str | None, str | None]]
    | tuple[tuple[str | None, str | None], ...]
    | list[dict],
) -> int:
    """Count isomorphic variants for R3 (deterministic).

    Args:
        occurrences: one entry per attempt where the target misconception
            was observed, each either a ``(problem_id, isomorphic_group_id)``
            pair or a dict with ``problem_id`` / ``isomorphic_group_id``
            keys. Entries with a missing/empty problem_id or group are
            skipped (legacy rows without group metadata never fire R3).

    Returns:
        Max distinct problem_id count within any single
        isomorphic_group_id (0 when no usable entry). R3 fires when this
        is >= VARIANT_THRESHOLD (2), i.e. >= 2 distinct problems sharing
        one group. Two problems from DIFFERENT groups yield 1, not 2.
    """
    if not isinstance(occurrences, (list, tuple)):
        raise TypeError(
            f"occurrences must be a list/tuple, got {type(occurrences).__name__}."
        )
    groups: dict[str, set[str]] = {}
    for entry in occurrences:
        if isinstance(entry, dict):
            if "problem_id" not in entry or "isomorphic_group_id" not in entry:
                raise ValueError(
                    "occurrences dicts need 'problem_id' + 'isomorphic_group_id' keys."
                )
            pid = entry["problem_id"]
            gid = entry["isomorphic_group_id"]
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            pid, gid = entry
        else:
            raise TypeError(
                "occurrences entries must be (problem_id, isomorphic_group_id) "
                f"pairs or dicts, got {entry!r}."
            )
        if pid is None or gid is None:
            continue
        if not isinstance(pid, str) or not isinstance(gid, str):
            raise TypeError(
                "problem_id/isomorphic_group_id must be str or None, "
                f"got {type(pid).__name__}/{type(gid).__name__}."
            )
        pid_text = pid.strip()
        gid_text = gid.strip()
        if not pid_text or not gid_text:
            continue
        groups.setdefault(gid_text, set()).add(pid_text)
    if not groups:
        return 0
    return max(len(problems) for problems in groups.values())


def has_improved(
    recent_attempts: list[tuple[bool, str | None]] | tuple[tuple[bool, str | None], ...] | list[dict],
    target_id: str,
    window: int = IMPROVEMENT_WINDOW,
) -> bool:
    """True iff the trailing ``window`` attempts show improvement.

    Improvement = at least ``window`` relevant attempts exist, ALL of the
    last ``window`` passed, and ``target_id`` appears in NONE of them.

    ``recent_attempts`` is oldest -> newest; each entry is either a
    ``(passed: bool, misconception_id: str | None)`` pair or a dict with
    keys ``passed`` / ``misconception_id``. This dual shape keeps the pure
    rule usable from both unit tests and the DB engine.
    """
    if type(window) is not int or window < 1:
        raise ValueError(f"window must be a positive int, got {window!r}.")
    if not isinstance(recent_attempts, (list, tuple)):
        raise TypeError(
            "recent_attempts must be a list/tuple, "
            f"got {type(recent_attempts).__name__}."
        )
    target = _normalize_mid(target_id)
    normalized: list[tuple[bool, str | None]] = []
    for entry in recent_attempts:
        if isinstance(entry, dict):
            if "passed" not in entry or "misconception_id" not in entry:
                raise ValueError(
                    "recent_attempts dicts need 'passed' + 'misconception_id' keys."
                )
            passed = entry["passed"]
            mid = entry["misconception_id"]
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            passed, mid = entry
        else:
            raise TypeError(
                "recent_attempts entries must be (passed, misconception_id) "
                f"pairs or dicts, got {entry!r}."
            )
        if not isinstance(passed, bool):
            raise TypeError(
                f"passed must be bool, got {type(passed).__name__}."
            )
        if mid is not None and not isinstance(mid, str):
            raise TypeError(
                f"misconception_id must be str or None, got {type(mid).__name__}."
            )
        normalized.append((passed, mid.strip().upper() if isinstance(mid, str) and mid.strip() else None))
    if len(normalized) < window:
        return False
    tail = normalized[-window:]
    if not all(passed for passed, _mid in tail):
        return False
    return all(mid != target for _passed, mid in tail)


__all__ = [
    "HISTORICAL_THRESHOLD",
    "IMPROVEMENT_WINDOW",
    "RECENT_THRESHOLD",
    "RECENT_WINDOW",
    "VARIANT_THRESHOLD",
    "check_recurring",
    "distinct_variant_count",
    "has_improved",
    "isomorphic_variant_count",
    "recent_occurrence_count",
]
