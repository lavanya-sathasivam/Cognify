"""COGNIFY ai-service — deterministic evidence-grounded diagnosis rules (Step 15).

Layer position (``service.diagnose_pack`` consults this FIRST)::

    EvidencePack -> deterministic rules -> (hit) grounded rule diagnosis
                                      -> (miss) existing LLM diagnosis
                                                  -> (unavailable/invalid) existing fallback

Ownership reminder: the Evidence Pack collects facts and never decides the
final misconception. This module INTERPRETS those facts: it selects among
the pack's candidate misconceptions, cites real evidence references, and
returns a confidence. It never writes learner state, never ranks next
actions, and never verifies improvement.

Properties (every rule):

- deterministic: pure function of the EvidencePack (stdlib AST + integer
  comparisons only). No clock, no randomness, no I/O, no environment.
- explainable: each rule has a stable ``rule_id`` and a short template
  explanation naming the observed evidence.
- grounded: ``evidence_refs`` use ONLY references the existing grounding
  validator accepts (``failed_test:<id>`` plus bare section names). Every
  rule-built diagnosis is re-checked with ``validate_llm_diagnosis`` and
  the confidence/grounding gate before it may fire; a rule that fails its
  own validation abstains.
- conservative: returns ``None`` (abstain) unless ALL required predicates
  hold. Never invents a misconception ID (targets must be pack
  candidates), never matches on problem ID, never picks the first or
  smallest candidate. Insufficient evidence -> no deterministic diagnosis.

Confidence: ``RULE_CONFIDENCE = 0.70``. Rationale: the acceptance floor is
0.50 (``gate.MIN_ACCEPT_CONFIDENCE``); each rule additionally requires TWO
independent evidence families (a static code-shape signal AND a dynamic
output signal) that corroborate each other, worth +0.10 each. The value
stays well below 1.0 because a deterministic rule is strong evidence, not
certainty. The module asserts the floor invariant at import time.

Current rules (C3 only, small set on purpose):

- ``C3_RANGE_BOUNDARY_EXCLUSION`` -> ``C3-M01`` (off-by-one-bounds):
  the Step 14 pattern ``for i in range(len(nums) - 1)`` where the terminal
  index is never visited. Requires: concept C3, Python, candidate C3-M01,
  status FAILED, code whose ``range`` stop is ``len(X) - 1``, a decisive
  failed test undercounting by exactly one, EVERY failed test
  undercounting by exactly one (uniform single-miss), and at least one
  passing test (surrounding logic works, isolating the defect to the
  missed terminal element).
- ``C3_RANGE_EXCLUSIVITY`` -> ``C3-M05`` (python-range-exclusivity):
  ``range(start, stop)`` with a constant start and an unadjusted bare-name
  stop (e.g. ``range(1, n)`` for an inclusive 1..n task). Requires:
  concept C3, Python, candidate C3-M05, status FAILED, that code shape,
  and EVERY failed test dropping exactly its terminal value
  (``actual == expected - n`` where ``n`` is the test's single input).
  No passing test is required: dropping the terminal value can fail every
  case (e.g. the n=1 boundary yields an empty range).

NOT implemented here: LLM calls, prompt building, the generic fallback
classifier (untouched in ``fallback.py``), mastery math, next-action
ranking, verification verdicts, database access.
"""
from __future__ import annotations

import ast as py_ast
from dataclasses import dataclass
from typing import Any

from packages.evidence.models import EvidencePack
from packages.taxonomy import get_misconception

from .gate import MIN_ACCEPT_CONFIDENCE, confidence_grounding_gate
from .models import Diagnosis
from .validator import DiagnosisValidationError, validate_llm_diagnosis

RULE_CONFIDENCE: float = 0.70

assert RULE_CONFIDENCE >= MIN_ACCEPT_CONFIDENCE, (
    "Rule confidence must satisfy the existing acceptance threshold."
)

FAILED_STATUS: str = "FAILED"
PYTHON_LANGUAGE: str = "python"
CONCEPT_C3: str = "C3"

TARGET_C3_M01: str = "C3-M01"
TARGET_C3_M05: str = "C3-M05"

RULE_C3_RANGE_BOUNDARY_EXCLUSION: str = "C3_RANGE_BOUNDARY_EXCLUSION"
RULE_C3_RANGE_EXCLUSIVITY: str = "C3_RANGE_EXCLUSIVITY"


@dataclass(frozen=True)
class EvidenceRule:
    """Static metadata for one deterministic rule (describes, never fires)."""

    rule_id: str
    target_misconception_id: str
    confidence: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "target_misconception_id": self.target_misconception_id,
            "confidence": self.confidence,
            "description": self.description,
        }


RULES: tuple[EvidenceRule, ...] = (
    EvidenceRule(
        rule_id=RULE_C3_RANGE_BOUNDARY_EXCLUSION,
        target_misconception_id=TARGET_C3_M01,
        confidence=RULE_CONFIDENCE,
        description=(
            "range(len(X) - 1) terminal-index exclusion with a uniform "
            "undercount-by-one across all failed tests."
        ),
    ),
    EvidenceRule(
        rule_id=RULE_C3_RANGE_EXCLUSIVITY,
        target_misconception_id=TARGET_C3_M05,
        confidence=RULE_CONFIDENCE,
        description=(
            "range(constant-start, bare-name stop) with every failed test "
            "dropping exactly its terminal value."
        ),
    ),
)


def _as_pack(pack: EvidencePack | dict[str, Any]) -> EvidencePack:
    if isinstance(pack, EvidencePack):
        return pack
    if isinstance(pack, dict):
        return EvidencePack.from_dict(pack)
    raise TypeError(f"pack must be EvidencePack or dict, got {type(pack).__name__}.")


def _candidate_ids(pack: EvidencePack) -> set[str]:
    return {c.misconception_id for c in pack.misconception_candidates}


def _parse_int_or_none(text: object) -> int | None:
    if not isinstance(text, str):
        return None
    try:
        return int(text.strip())
    except (ValueError, TypeError):
        return None


def _parse_single_input_n(text: object) -> int | None:
    """Parse a test input holding exactly one integer (e.g. ``"5\\n"``)."""
    if not isinstance(text, str):
        return None
    parts = text.strip().split()
    if len(parts) != 1:
        return None
    try:
        value = int(parts[0])
    except (ValueError, TypeError):
        return None
    return value if value >= 1 else None


def _iter_range_calls(code: str) -> list[py_ast.Call]:
    try:
        tree = py_ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return []
    calls: list[py_ast.Call] = []
    for node in py_ast.walk(tree):
        if not isinstance(node, py_ast.Call):
            continue
        func = node.func
        if isinstance(func, py_ast.Name) and func.id == "range":
            calls.append(node)
    return calls


def _is_len_minus_one(expr: py_ast.expr) -> bool:
    """True for ``len(X) - 1`` (any spacing, any variable name)."""
    if not isinstance(expr, py_ast.BinOp) or not isinstance(expr.op, py_ast.Sub):
        return False
    left, right = expr.left, expr.right
    if not (
        isinstance(left, py_ast.Call)
        and isinstance(left.func, py_ast.Name)
        and left.func.id == "len"
        and len(left.args) == 1
    ):
        return False
    return isinstance(right, py_ast.Constant) and right.value == 1


def _code_excludes_terminal_index(code: str) -> tuple[bool, str | None]:
    """Detect ``range(..., len(X) - 1)`` (single- or multi-arg form).

    Returns ``(found, snippet)`` where ``snippet`` is the deterministic
    source rendering of the first matching ``range(...)`` call.
    """
    if not isinstance(code, str) or not code.strip():
        return False, None
    for call in _iter_range_calls(code):
        if not call.args:
            continue
        if _is_len_minus_one(call.args[-1]):
            try:
                snippet = py_ast.unparse(call)
            except (ValueError, RecursionError):
                snippet = "range(..., len(...) - 1)"
            return True, snippet
    return False, None


def _code_has_unadjusted_range_stop(code: str) -> tuple[bool, str | None]:
    """Detect ``range(<int start>, <bare-name stop>)`` e.g. ``range(1, n)``.

    A bare-name stop carries no ``+ 1`` adjustment, so for an inclusive
    upper-bound task the terminal value is excluded. Single-arg
    ``range(n)`` is NOT matched (correct 0..n-1 shape for counting tasks).
    """
    if not isinstance(code, str) or not code.strip():
        return False, None
    for call in _iter_range_calls(code):
        if len(call.args) < 2:
            continue
        first, last = call.args[0], call.args[-1]
        if not (isinstance(first, py_ast.Constant) and isinstance(first.value, int)):
            continue
        if not isinstance(last, py_ast.Name):
            continue
        try:
            snippet = py_ast.unparse(call)
        except (ValueError, RecursionError):
            snippet = "range(<start>, <stop>)"
        return True, snippet
    return False, None


def _truncate(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _rule_refs(pack: EvidencePack) -> list[str]:
    decisive = pack.failed_tests[0].test_id
    return [f"failed_test:{decisive}", "expected_output", "actual_output", "code"]


def _checked(rule_id: str, diagnosis: Diagnosis, pack: EvidencePack) -> Diagnosis | None:
    """Re-validate a rule-built diagnosis with the existing validator+gate.

    Returns the validated diagnosis, or ``None`` when our own output fails
    the acceptance bar (a rule that cannot prove itself abstains).
    """
    try:
        validated = validate_llm_diagnosis(diagnosis.to_dict(), pack)
    except (DiagnosisValidationError, ValueError, TypeError, AttributeError):
        return None
    accepted, _reason = confidence_grounding_gate(validated, pack)
    if not accepted:
        return None
    if validated.misconception_id not in _candidate_ids(pack):
        return None
    if validated.concept_id != pack.concept_id:
        return None
    _ = rule_id  # rule identity travels in the explanation, not the schema.
    return validated


def _match_range_boundary_exclusion(pack: EvidencePack) -> Diagnosis | None:
    """Rule ``C3_RANGE_BOUNDARY_EXCLUSION`` -> ``C3-M01`` (or abstain)."""
    if pack.concept_id != CONCEPT_C3 or pack.language != PYTHON_LANGUAGE:
        return None
    if TARGET_C3_M01 not in _candidate_ids(pack):
        return None
    if pack.execution_status != FAILED_STATUS or not pack.failed_tests:
        return None
    found, snippet = _code_excludes_terminal_index(pack.code)
    if not found:
        return None
    for failed in pack.failed_tests:
        expected = _parse_int_or_none(failed.expected_output)
        actual = _parse_int_or_none(failed.actual_output)
        if expected is None or actual is None:
            return None
        if expected < 1 or actual != expected - 1:
            return None
    if pack.passed_count < 1:
        return None
    decisive = pack.failed_tests[0]
    expected = _parse_int_or_none(decisive.expected_output)
    actual = _parse_int_or_none(decisive.actual_output)
    assert expected is not None and actual is not None
    name = get_misconception(TARGET_C3_M01).name
    explanation = _truncate(
        f"Rule {RULE_C3_RANGE_BOUNDARY_EXCLUSION}: the code iterates "
        f"{snippet}, excluding the terminal index, and every failed test "
        f"undercounts by exactly one (decisive {decisive.test_id}: expected "
        f"{expected}, got {actual}). This matches {TARGET_C3_M01} {name}."
    )
    candidate = Diagnosis(
        concept_id=pack.concept_id,
        misconception_id=TARGET_C3_M01,
        confidence=RULE_CONFIDENCE,
        explanation=explanation,
        evidence_refs=_rule_refs(pack),
    )
    return _checked(RULE_C3_RANGE_BOUNDARY_EXCLUSION, candidate, pack)


def _match_range_exclusivity(pack: EvidencePack) -> Diagnosis | None:
    """Rule ``C3_RANGE_EXCLUSIVITY`` -> ``C3-M05`` (or abstain)."""
    if pack.concept_id != CONCEPT_C3 or pack.language != PYTHON_LANGUAGE:
        return None
    if TARGET_C3_M05 not in _candidate_ids(pack):
        return None
    if pack.execution_status != FAILED_STATUS or not pack.failed_tests:
        return None
    found, snippet = _code_has_unadjusted_range_stop(pack.code)
    if not found:
        return None
    for failed in pack.failed_tests:
        n = _parse_single_input_n(failed.input)
        expected = _parse_int_or_none(failed.expected_output)
        actual = _parse_int_or_none(failed.actual_output)
        if n is None or expected is None or actual is None:
            return None
        if actual != expected - n:
            return None
    decisive = pack.failed_tests[0]
    n = _parse_single_input_n(decisive.input)
    expected = _parse_int_or_none(decisive.expected_output)
    actual = _parse_int_or_none(decisive.actual_output)
    assert n is not None and expected is not None and actual is not None
    name = get_misconception(TARGET_C3_M05).name
    explanation = _truncate(
        f"Rule {RULE_C3_RANGE_EXCLUSIVITY}: the code iterates {snippet} "
        f"with an unadjusted stop, and every failed test drops exactly its "
        f"terminal value (decisive {decisive.test_id}: n={n}, expected "
        f"{expected}, got {actual}). This matches {TARGET_C3_M05} {name}."
    )
    candidate = Diagnosis(
        concept_id=pack.concept_id,
        misconception_id=TARGET_C3_M05,
        confidence=RULE_CONFIDENCE,
        explanation=explanation,
        evidence_refs=_rule_refs(pack),
    )
    return _checked(RULE_C3_RANGE_EXCLUSIVITY, candidate, pack)


def try_rule_diagnosis(pack: EvidencePack | dict[str, Any]) -> Diagnosis | None:
    """Apply deterministic evidence rules to one EvidencePack.

    Returns the first firing rule's validated :class:`Diagnosis`, or
    ``None`` when no rule's evidence predicates are fully satisfied
    (callers then fall through to the LLM / generic fallback paths).
    Pure and deterministic: equal packs yield equal results.
    """
    evidence = _as_pack(pack)
    for matcher in (_match_range_boundary_exclusion, _match_range_exclusivity):
        hit = matcher(evidence)
        if hit is not None:
            return hit
    return None


__all__ = [
    "CONCEPT_C3",
    "FAILED_STATUS",
    "PYTHON_LANGUAGE",
    "RULES",
    "RULE_CONFIDENCE",
    "RULE_C3_RANGE_BOUNDARY_EXCLUSION",
    "RULE_C3_RANGE_EXCLUSIVITY",
    "TARGET_C3_M01",
    "TARGET_C3_M05",
    "EvidenceRule",
    "try_rule_diagnosis",
]
