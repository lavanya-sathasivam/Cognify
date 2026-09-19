"""COGNIFY mastery — package init (Step 8).

Deterministic, stdlib-only shared mastery formula + recurring-weakness rules.

- ``formula``: mastery bands, failure severity, deterministic mastery update,
  trend / hint-dependence / transfer-rate helpers. Pure: same inputs always
  produce the same outputs. No clock, no randomness, no I/O, no DB, no LLM.
- ``weakness``: recurring-weakness + improvement predicates over plain data.
  Pure: operates on counts / ID lists supplied by callers (core-backend
  derives them from its tables). No DB access here.

Core-backend owns all database mutations (see
``services/core-backend/app/learner_engine.py``); the AI service must never
import this package's callers' DB layer — it only reads EvidencePacks.
"""

from .formula import (
    FAIL_SEVERITY_SCALE,
    FAIL_BASE_PENALTY,
    HINT_DAMPING,
    HINT_FAIL_PENALTY,
    INITIAL_MASTERY,
    MAX_MASTERY,
    MIN_MASTERY,
    MOMENTUM_SCALE,
    PASS_BASE_GAIN,
    TRANSFER_BONUS,
    TRANSFER_FAIL_PENALTY,
    clamp_mastery,
    compute_mastery_update,
    compute_trend,
    hint_dependence_rate,
    is_transfer_variant,
    mastery_band,
    recent_pass_rate,
    severity_for_status,
)
from .weakness import (
    HISTORICAL_THRESHOLD,
    IMPROVEMENT_WINDOW,
    RECENT_THRESHOLD,
    RECENT_WINDOW,
    VARIANT_THRESHOLD,
    check_recurring,
    distinct_variant_count,
    has_improved,
    isomorphic_variant_count,
    recent_occurrence_count,
)

__all__ = [
    "FAIL_SEVERITY_SCALE",
    "FAIL_BASE_PENALTY",
    "HISTORICAL_THRESHOLD",
    "HINT_DAMPING",
    "HINT_FAIL_PENALTY",
    "IMPROVEMENT_WINDOW",
    "INITIAL_MASTERY",
    "MAX_MASTERY",
    "MIN_MASTERY",
    "MOMENTUM_SCALE",
    "PASS_BASE_GAIN",
    "RECENT_THRESHOLD",
    "RECENT_WINDOW",
    "TRANSFER_BONUS",
    "TRANSFER_FAIL_PENALTY",
    "VARIANT_THRESHOLD",
    "check_recurring",
    "clamp_mastery",
    "compute_mastery_update",
    "compute_trend",
    "distinct_variant_count",
    "has_improved",
    "hint_dependence_rate",
    "is_transfer_variant",
    "isomorphic_variant_count",
    "mastery_band",
    "recent_occurrence_count",
    "recent_pass_rate",
    "severity_for_status",
]
