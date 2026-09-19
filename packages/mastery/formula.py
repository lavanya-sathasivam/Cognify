"""COGNIFY mastery — deterministic mastery formula (Step 8).

Pure function of its inputs: the same evidence always produces the same
mastery transition. No LLM, no clock, no randomness, no I/O, no DB.

Mastery range: [0.0, 1.0]. Initial mastery for a new (user, track, concept)
is 0.20 (novice).

Bands (spec):
  < 0.40            -> novice
  0.40 .. 0.59      -> emerging
  0.60 .. 0.79      -> proficient
  >= 0.80           -> mastered

Formula (additive, clamped, rounded to 4 decimals):

  On PASS (execution_status == "PASSED"):
    base_gain   = PASS_BASE_GAIN (0.12)
    if hint_used: base_gain *= HINT_DAMPING (0.5)   # independence matters
    if is_transfer: base_gain += TRANSFER_BONUS (0.04)
    momentum    = (recent_pass_rate - 0.5) * MOMENTUM_SCALE (0.04)
    delta       = base_gain + momentum              # in [0.04, 0.18]

  On FAIL (any non-PASSED terminal status):
    severity      = severity_for_status(execution_status)  # 0.5..1.0
    base_penalty  = -(FAIL_BASE_PENALTY + FAIL_SEVERITY_SCALE * severity)
                    # FAILED -> -0.085, COMPILE/RUNTIME -> -0.1025, TIMEOUT -> -0.12
    if hint_used:  base_penalty -= HINT_FAIL_PENALTY (0.02)
    if is_transfer: base_penalty -= TRANSFER_FAIL_PENALTY (0.01)
    momentum      = (recent_pass_rate - 0.5) * MOMENTUM_SCALE
    delta         = base_penalty + momentum          # in [-0.17, -0.065]

  new = clamp(round(previous + delta, 4))

``recent_pass_rate`` is the pass rate over prior relevant attempts for the
concept (0.0..1.0). Callers with no history MUST pass 0.5 (neutral) so the
first attempt has zero momentum. ``compute_trend`` / ``hint_dependence_rate``
/ ``transfer_success_rate`` helpers are also pure and deterministic.
"""
from __future__ import annotations

INITIAL_MASTERY: float = 0.20
MIN_MASTERY: float = 0.0
MAX_MASTERY: float = 1.0

PASS_BASE_GAIN: float = 0.12
TRANSFER_BONUS: float = 0.04
HINT_DAMPING: float = 0.5
MOMENTUM_SCALE: float = 0.04

FAIL_BASE_PENALTY: float = 0.05
FAIL_SEVERITY_SCALE: float = 0.07
HINT_FAIL_PENALTY: float = 0.02
TRANSFER_FAIL_PENALTY: float = 0.01

BAND_NOVICE: str = "novice"
BAND_EMERGING: str = "emerging"
BAND_PROFICIENT: str = "proficient"
BAND_MASTERED: str = "mastered"

SEVERITY_BY_STATUS: dict[str, float] = {
    "PASSED": 0.0,
    "FAILED": 0.5,
    "COMPILE_ERROR": 0.75,
    "RUNTIME_ERROR": 0.75,
    "TIMEOUT": 1.0,
}

VALID_STATUSES: tuple[str, ...] = tuple(SEVERITY_BY_STATUS.keys())


def _require_mastery(value: object, field_name: str = "mastery") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number, got {type(value).__name__}.")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be in [0, 1], got {value!r}.")
    return number


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool, got {type(value).__name__}.")
    return value


def _require_rate(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number, got {type(value).__name__}.")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be in [0, 1], got {value!r}.")
    return number


def clamp_mastery(value: float) -> float:
    """Clamp ``value`` into [0.0, 1.0] (numeric input required)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"value must be a number, got {type(value).__name__}.")
    number = float(value)
    if number < MIN_MASTERY:
        return MIN_MASTERY
    if number > MAX_MASTERY:
        return MAX_MASTERY
    return number


def mastery_band(mastery: float) -> str:
    """Map a mastery score in [0, 1] to its band (deterministic)."""
    score = _require_mastery(mastery, "mastery")
    if score < 0.40:
        return BAND_NOVICE
    if score < 0.60:
        return BAND_EMERGING
    if score < 0.80:
        return BAND_PROFICIENT
    return BAND_MASTERED


def severity_for_status(execution_status: str) -> float:
    """Map an execution status to failure severity in [0.0, 1.0].

    PASSED -> 0.0, FAILED (wrong output) -> 0.5,
    COMPILE_ERROR / RUNTIME_ERROR -> 0.75, TIMEOUT -> 1.0.
    Input is case/space tolerant.
    """
    if not isinstance(execution_status, str):
        raise TypeError(
            f"execution_status must be str, got {type(execution_status).__name__}."
        )
    norm = execution_status.strip().upper()
    if norm not in SEVERITY_BY_STATUS:
        raise ValueError(
            f"Unknown execution_status {execution_status!r}. "
            f"Use one of {list(VALID_STATUSES)}."
        )
    return SEVERITY_BY_STATUS[norm]


def normalize_execution_status(execution_status: str) -> str:
    """Strip + upper-case; raises ValueError if unknown status."""
    severity_for_status(execution_status)  # validates
    assert isinstance(execution_status, str)
    return execution_status.strip().upper()


def compute_mastery_update(
    previous: float,
    passed: bool,
    execution_status: str,
    hint_used: bool,
    is_transfer: bool,
    recent_pass_rate: float,
) -> tuple[float, float, str]:
    """Compute the deterministic mastery transition for one attempt.

    Args:
        previous: mastery before this attempt, in [0, 1].
        passed: True iff the submission passed (must agree with
            ``execution_status == "PASSED"``).
        execution_status: terminal execution outcome (PASSED / FAILED /
            COMPILE_ERROR / RUNTIME_ERROR / TIMEOUT, case tolerant).
        hint_used: True iff a hint was used for this attempt.
        is_transfer: True iff the problem is a transfer/isomorphic variant.
        recent_pass_rate: pass rate over prior relevant attempts in [0, 1];
            pass 0.5 when there is no history (neutral momentum).

    Returns:
        ``(new_mastery, delta, reason)`` where ``new_mastery`` is clamped to
        [0, 1] and rounded to 4 decimals, ``delta = new - previous``
        (rounded to 4), and ``reason`` is a deterministic human-readable
        tag encoding the evidence branch taken.

    Raises:
        TypeError / ValueError: on any invalid input or on
            passed/status disagreement.
    """
    prev = _require_mastery(previous, "previous")
    _require_bool(passed, "passed")
    _require_bool(hint_used, "hint_used")
    _require_bool(is_transfer, "is_transfer")
    rate = _require_rate(recent_pass_rate, "recent_pass_rate")
    severity = severity_for_status(execution_status)
    status_norm = execution_status.strip().upper()

    if passed and status_norm != "PASSED":
        raise ValueError(
            f"passed=True disagrees with execution_status {status_norm!r} "
            "(must be 'PASSED')."
        )
    if not passed and status_norm == "PASSED":
        raise ValueError(
            "passed=False disagrees with execution_status 'PASSED'."
        )

    momentum = (rate - 0.5) * MOMENTUM_SCALE
    if passed:
        base = PASS_BASE_GAIN
        branch = "pass"
        if hint_used:
            base *= HINT_DAMPING
            branch += "+hint"
        else:
            branch += "+independent"
        if is_transfer:
            base += TRANSFER_BONUS
            branch += "+transfer"
        else:
            branch += "+canonical"
        if rate >= 0.8:
            branch += "+hot-streak"
        elif rate <= 0.2:
            branch += "+cold-start"
        delta = base + momentum
        reason = (
            f"{branch} (recent {rate:.2f}, momentum {momentum:+.3f}, "
            f"base {base:+.3f})"
        )
    else:
        base = -(FAIL_BASE_PENALTY + FAIL_SEVERITY_SCALE * severity)
        branch = f"fail/{status_norm.lower()}"
        if hint_used:
            base -= HINT_FAIL_PENALTY
            branch += "+hint"
        else:
            branch += "+independent"
        if is_transfer:
            base -= TRANSFER_FAIL_PENALTY
            branch += "+transfer"
        else:
            branch += "+canonical"
        if rate >= 0.8:
            branch += "+hot-streak-cushioned"
        elif rate <= 0.2:
            branch += "+cold-streak"
        delta = base + momentum
        reason = (
            f"{branch} (severity {severity:.2f}, recent {rate:.2f}, "
            f"momentum {momentum:+.3f}, base {base:+.3f})"
        )

    new_raw = prev + delta
    new = round(clamp_mastery(new_raw), 4)
    delta_out = round(new - prev, 4)
    return new, delta_out, reason


def compute_trend(recent_outcomes: list[bool] | tuple[bool, ...]) -> str:
    """Map recent pass/fail outcomes (oldest -> newest) to a trend.

    - [] -> "unknown" (no history).
    - last up-to-3 all True (and >= 2 outcomes) -> "improving".
    - last up-to-3 all False (and >= 2 outcomes) -> "declining".
    - otherwise -> "stable" (includes single-attempt histories).
    """
    if not isinstance(recent_outcomes, (list, tuple)):
        raise TypeError(
            "recent_outcomes must be a list/tuple of bool, "
            f"got {type(recent_outcomes).__name__}."
        )
    for item in recent_outcomes:
        if not isinstance(item, bool):
            raise TypeError(
                f"recent_outcomes entries must be bool, got {type(item).__name__}."
            )
    if len(recent_outcomes) == 0:
        return "unknown"
    window = list(recent_outcomes[-3:])
    if len(window) >= 2 and all(window):
        return "improving"
    if len(window) >= 2 and not any(window):
        return "declining"
    return "stable"


def recent_pass_rate(
    recent_outcomes: list[bool] | tuple[bool, ...], window: int = 5
) -> float:
    """Pass rate over the trailing ``window`` outcomes (0.0..1.0).

    Empty history yields 0.5 (neutral momentum for the formula). Callers
    that need to distinguish "no history" from "50%" should check the
    input length separately.
    """
    if type(window) is not int or window < 1:
        raise ValueError(f"window must be a positive int, got {window!r}.")
    if not isinstance(recent_outcomes, (list, tuple)):
        raise TypeError(
            "recent_outcomes must be a list/tuple of bool, "
            f"got {type(recent_outcomes).__name__}."
        )
    for item in recent_outcomes:
        if not isinstance(item, bool):
            raise TypeError(
                f"recent_outcomes entries must be bool, got {type(item).__name__}."
            )
    if len(recent_outcomes) == 0:
        return 0.5
    tail = list(recent_outcomes[-window:])
    return round(sum(1 for ok in tail if ok) / len(tail), 4)


def hint_dependence_rate(hint_count: int, attempt_count: int) -> float:
    """Fraction of attempts that used a hint (0.0 when no attempts)."""
    if type(hint_count) is not int or hint_count < 0:
        raise ValueError(f"hint_count must be a non-negative int, got {hint_count!r}.")
    if type(attempt_count) is not int or attempt_count < 0:
        raise ValueError(
            f"attempt_count must be a non-negative int, got {attempt_count!r}."
        )
    if hint_count > attempt_count:
        raise ValueError(
            f"hint_count ({hint_count}) cannot exceed attempt_count ({attempt_count})."
        )
    if attempt_count == 0:
        return 0.0
    return round(hint_count / attempt_count, 4)


def transfer_success_rate(successes: int, attempts: int) -> float:
    """Transfer success fraction (0.0 when no transfer attempts)."""
    if type(successes) is not int or successes < 0:
        raise ValueError(f"successes must be a non-negative int, got {successes!r}.")
    if type(attempts) is not int or attempts < 0:
        raise ValueError(f"attempts must be a non-negative int, got {attempts!r}.")
    if successes > attempts:
        raise ValueError(
            f"successes ({successes}) cannot exceed attempts ({attempts})."
        )
    if attempts == 0:
        return 0.0
    return round(successes / attempts, 4)


def is_transfer_variant(variant_role: str) -> bool:
    """True iff ``variant_role`` names a transfer variant (case tolerant)."""
    if not isinstance(variant_role, str):
        raise TypeError(
            f"variant_role must be str, got {type(variant_role).__name__}."
        )
    return variant_role.strip().lower() == "transfer"


__all__ = [
    "BAND_EMERGING",
    "BAND_MASTERED",
    "BAND_NOVICE",
    "BAND_PROFICIENT",
    "FAIL_BASE_PENALTY",
    "FAIL_SEVERITY_SCALE",
    "HINT_DAMPING",
    "HINT_FAIL_PENALTY",
    "INITIAL_MASTERY",
    "MAX_MASTERY",
    "MIN_MASTERY",
    "MOMENTUM_SCALE",
    "PASS_BASE_GAIN",
    "SEVERITY_BY_STATUS",
    "TRANSFER_BONUS",
    "TRANSFER_FAIL_PENALTY",
    "VALID_STATUSES",
    "clamp_mastery",
    "compute_mastery_update",
    "compute_trend",
    "hint_dependence_rate",
    "is_transfer_variant",
    "mastery_band",
    "normalize_execution_status",
    "recent_pass_rate",
    "severity_for_status",
    "transfer_success_rate",
]
