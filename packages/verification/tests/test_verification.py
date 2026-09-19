"""Unit tests for Step 10: Deterministic Verification Engine.

Pure, deterministic, stdlib + unittest only. No DB, no LLM, no network,
no code execution, no mastery calculation, no adaptive ranking.

Run from repo root:
    python -m unittest discover -s packages/verification/tests -t . -v
"""
from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.verification import (  # noqa: E402
    ExecutionOutcome,
    ReasonCode,
    VerificationAttempt,
    VerificationContext,
    VerificationOutcome,
    VerificationResult,
    build_reason,
    to_learner_evidence,
    verify_improvement,
)
from packages.verification import engine as engine_module  # noqa: E402

ORIG = "PY-C3-001"
TRANS = "PY-C3-002"
CONCEPT = "C3"
TRACK = "python"
TARGET = "C3-M01"
GROUP = "ISO-C3-01"


def _attempt(
    problem_id=ORIG,
    concept_id=CONCEPT,
    track=TRACK,
    outcome="PASS",
    misconception_id=None,
    is_transfer=None,
    iso=None,
):
    return VerificationAttempt(
        problem_id=problem_id,
        concept_id=concept_id,
        language_track=track,
        outcome=outcome,
        misconception_id=misconception_id,
        is_transfer=is_transfer,
        isomorphic_group_id=iso,
    )


def _context(
    original_outcome="PASS",
    transfer_outcome="PASS",
    transfer_pid=TRANS,
    target=TARGET,
    track=TRACK,
    concept=CONCEPT,
    level="hint-L2",
    orig_is_transfer=None,
    trans_is_transfer=True,
    iso=GROUP,
    include_original=True,
    include_transfer=True,
):
    original = None
    if include_original:
        if original_outcome is None:
            original = None
        else:
            original = _attempt(
                problem_id=ORIG,
                concept_id=concept if track == TRACK else concept,
                track=track,
                outcome=original_outcome,
                is_transfer=orig_is_transfer,
                iso=iso,
            )
    transfer = None
    if include_transfer:
        if transfer_outcome is None:
            transfer = None
        else:
            # Transfer attempt must live on the context track/concept unless
            # the test deliberately wants a mismatch (then it builds raw).
            transfer = _attempt(
                problem_id=transfer_pid,
                concept_id=concept,
                track=track,
                outcome=transfer_outcome,
                is_transfer=trans_is_transfer,
                iso=iso,
            )
    return VerificationContext(
        original_problem_id=ORIG,
        transfer_problem_id=transfer_pid,
        concept_id=concept,
        language_track=track,
        target_misconception_id=target,
        intervention_level=level,
        original_retry=original,
        transfer=transfer,
        isomorphic_group_id=iso,
    )


# ---------------------------------------------------------------------------
# 1-4. Original non-PASS -> NOT_IMPROVED
# ---------------------------------------------------------------------------
class OriginalNonPassTests(unittest.TestCase):
    def test_original_fail_not_improved(self):
        ctx = _context(original_outcome="FAIL", transfer_outcome="PASS")
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.NOT_IMPROVED)
        self.assertEqual(res.reason_code, ReasonCode.ORIGINAL_RETRY_FAILED)
        self.assertFalse(res.original_passed)
        self.assertTrue(res.transfer_passed)

    def test_original_compile_error_not_improved(self):
        ctx = _context(original_outcome="COMPILE_ERROR", transfer_outcome="PASS")
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.NOT_IMPROVED)
        self.assertEqual(res.reason_code, ReasonCode.ORIGINAL_RETRY_FAILED)
        self.assertFalse(res.original_passed)

    def test_original_runtime_error_not_improved(self):
        ctx = _context(original_outcome="RUNTIME_ERROR", transfer_outcome=None,
                       transfer_pid=TRANS)
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.NOT_IMPROVED)
        self.assertFalse(res.original_passed)
        self.assertFalse(res.transfer_passed)

    def test_original_timeout_not_improved(self):
        ctx = _context(original_outcome="TIMEOUT", transfer_outcome="FAIL")
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.NOT_IMPROVED)
        self.assertEqual(res.reason_code, ReasonCode.ORIGINAL_RETRY_FAILED)

    def test_original_fail_dominates_even_when_transfer_passes(self):
        ctx = _context(original_outcome="FAIL", transfer_outcome="PASS")
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.NOT_IMPROVED)
        # Never claim verified when the original retry did not pass.
        self.assertNotEqual(res.outcome, VerificationOutcome.VERIFIED_IMPROVED)


# ---------------------------------------------------------------------------
# 5-7. Core decision table
# ---------------------------------------------------------------------------
class DecisionTableTests(unittest.TestCase):
    def test_original_pass_transfer_missing_incomplete(self):
        ctx = _context(original_outcome="PASS", transfer_outcome=None)
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.INCOMPLETE)
        self.assertEqual(
            res.reason_code, ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_MISSING
        )
        self.assertTrue(res.original_passed)
        self.assertFalse(res.transfer_passed)

    def test_original_pass_transfer_fail_surface_fix(self):
        ctx = _context(original_outcome="PASS", transfer_outcome="FAIL")
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.SURFACE_FIX)
        self.assertEqual(
            res.reason_code, ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_FAILED
        )
        self.assertTrue(res.original_passed)
        self.assertFalse(res.transfer_passed)

    def test_original_pass_transfer_pass_verified_improved(self):
        ctx = _context(original_outcome="PASS", transfer_outcome="PASS")
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.VERIFIED_IMPROVED)
        self.assertEqual(
            res.reason_code, ReasonCode.ORIGINAL_AND_TRANSFER_PASSED
        )
        self.assertTrue(res.original_passed)
        self.assertTrue(res.transfer_passed)

    def test_both_missing_incomplete(self):
        ctx = _context(original_outcome=None, transfer_outcome=None,
                       include_original=False, include_transfer=False)
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.INCOMPLETE)
        self.assertEqual(res.reason_code, ReasonCode.ORIGINAL_RETRY_MISSING)

    def test_original_missing_transfer_pass_still_incomplete(self):
        # Transfer alone must never verify improvement.
        transfer_only = _attempt(
            problem_id=TRANS, outcome="PASS", is_transfer=True, iso=None,
        )
        ctx = VerificationContext(
            original_problem_id=ORIG,
            transfer_problem_id=TRANS,
            concept_id=CONCEPT,
            language_track=TRACK,
            original_retry=None,
            transfer=transfer_only,
            isomorphic_group_id=None,
        )
        res = verify_improvement(ctx)
        self.assertEqual(res.outcome, VerificationOutcome.INCOMPLETE)
        self.assertEqual(res.reason_code, ReasonCode.ORIGINAL_RETRY_MISSING)
        self.assertNotEqual(res.outcome, VerificationOutcome.VERIFIED_IMPROVED)

    def test_pass_plus_transfer_error_variants_are_surface_fix(self):
        for status in ("COMPILE_ERROR", "RUNTIME_ERROR", "TIMEOUT", "FAIL"):
            with self.subTest(transfer=status):
                ctx = _context(original_outcome="PASS", transfer_outcome=status)
                res = verify_improvement(ctx)
                self.assertEqual(res.outcome, VerificationOutcome.SURFACE_FIX)
                self.assertEqual(
                    res.reason_code,
                    ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_FAILED,
                )


# ---------------------------------------------------------------------------
# 8-11. Input validation
# ---------------------------------------------------------------------------
class ValidationTests(unittest.TestCase):
    def test_malformed_language_rejected(self):
        with self.assertRaises(ValueError):
            _attempt(track="javascript")
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                concept_id=CONCEPT,
                language_track="javascript",
            )

    def test_cross_language_original_transfer_rejected(self):
        transfer_java = VerificationAttempt(
            problem_id=TRANS,
            concept_id=CONCEPT,
            language_track="java",
            outcome="PASS",
            is_transfer=True,
        )
        original_py = _attempt(outcome="PASS", iso=None)
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                transfer_problem_id=TRANS,
                concept_id=CONCEPT,
                language_track="python",
                original_retry=original_py,
                transfer=transfer_java,
            )

    def test_same_original_and_transfer_problem_rejected(self):
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                transfer_problem_id=ORIG,
                concept_id=CONCEPT,
                language_track=TRACK,
            )

    def test_concept_mismatch_rejected(self):
        other = _attempt(problem_id=ORIG, concept_id="C4", outcome="PASS", iso=None)
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                transfer_problem_id=TRANS,
                concept_id=CONCEPT,
                language_track=TRACK,
                original_retry=other,
            )

    def test_unknown_concept_rejected(self):
        with self.assertRaises(ValueError):
            _attempt(concept_id="C99")

    def test_unknown_misconception_rejected(self):
        with self.assertRaises(ValueError):
            _attempt(misconception_id="C3-M99")

    def test_misconception_from_other_concept_rejected(self):
        with self.assertRaises(ValueError):
            _attempt(concept_id="C3", misconception_id="C4-M01")

    def test_original_problem_id_mismatch_rejected(self):
        wrong = _attempt(problem_id="PY-C3-999", outcome="PASS", iso=None)
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                concept_id=CONCEPT,
                language_track=TRACK,
                original_retry=wrong,
            )

    def test_transfer_without_transfer_problem_id_rejected(self):
        transfer = _attempt(problem_id=TRANS, outcome="PASS", is_transfer=True, iso=None)
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                concept_id=CONCEPT,
                language_track=TRACK,
                transfer_problem_id=None,
                transfer=transfer,
            )

    def test_original_flagged_as_transfer_rejected(self):
        bad = _attempt(outcome="PASS", is_transfer=True, iso=None)
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                concept_id=CONCEPT,
                language_track=TRACK,
                original_retry=bad,
            )

    def test_transfer_flagged_as_non_transfer_rejected(self):
        bad = _attempt(
            problem_id=TRANS, outcome="PASS", is_transfer=False, iso=None,
        )
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                transfer_problem_id=TRANS,
                concept_id=CONCEPT,
                language_track=TRACK,
                transfer=bad,
            )

    def test_contradictory_isomorphic_group_rejected(self):
        original = _attempt(outcome="PASS", iso="ISO-C3-01")
        transfer = _attempt(
            problem_id=TRANS, outcome="PASS", is_transfer=True, iso="ISO-C3-02",
        )
        with self.assertRaises(ValueError):
            VerificationContext(
                original_problem_id=ORIG,
                transfer_problem_id=TRANS,
                concept_id=CONCEPT,
                language_track=TRACK,
                original_retry=original,
                transfer=transfer,
                isomorphic_group_id="ISO-C3-01",
            )

    def test_empty_problem_id_rejected(self):
        with self.assertRaises((TypeError, ValueError)):
            _attempt(problem_id="   ")

    def test_verify_rejects_non_context(self):
        with self.assertRaises(TypeError):
            verify_improvement({"not": "a context"})  # type: ignore[arg-type]

    def test_result_outcome_reason_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            VerificationResult(
                outcome="VERIFIED_IMPROVED",
                reason_code="ORIGINAL_RETRY_FAILED",
                reason="Deliberately inconsistent outcome and reason code here.",
                concept_id=CONCEPT,
                language_track=TRACK,
                original_problem_id=ORIG,
                transfer_problem_id=TRANS,
                target_misconception_id=None,
                original_passed=True,
                transfer_passed=True,
                evidence=["e1"],
                original_outcome="PASS",
                transfer_outcome="PASS",
            )


# ---------------------------------------------------------------------------
# 12-14. Preservation, reason codes, determinism
# ---------------------------------------------------------------------------
class PreservationAndDeterminismTests(unittest.TestCase):
    def test_target_misconception_preserved(self):
        ctx = _context(target=TARGET)
        res = verify_improvement(ctx)
        self.assertEqual(res.target_misconception_id, TARGET)

    def test_target_misconception_none_preserved(self):
        ctx = _context(target=None)
        res = verify_improvement(ctx)
        self.assertIsNone(res.target_misconception_id)

    def test_reason_codes_cover_each_branch(self):
        cases = [
            (_context(original_outcome="FAIL", transfer_outcome="PASS"),
             ReasonCode.ORIGINAL_RETRY_FAILED),
            (_context(original_outcome="PASS", transfer_outcome=None),
             ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_MISSING),
            (_context(original_outcome="PASS", transfer_outcome="FAIL"),
             ReasonCode.ORIGINAL_RETRY_PASSED_TRANSFER_FAILED),
            (_context(original_outcome="PASS", transfer_outcome="PASS"),
             ReasonCode.ORIGINAL_AND_TRANSFER_PASSED),
        ]
        for ctx, expected in cases:
            with self.subTest(expected=expected):
                res = verify_improvement(ctx)
                self.assertEqual(res.reason_code, expected)
                self.assertGreaterEqual(len(res.reason), 10)
                # Reason text is deterministic for the branch.
                again = verify_improvement(ctx)
                self.assertEqual(res.reason, again.reason)

    def test_repeated_identical_input_produces_identical_result(self):
        ctx = _context()
        first = verify_improvement(ctx)
        second = verify_improvement(ctx)
        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.evidence, second.evidence)

    def test_evidence_is_deterministic_and_nonempty(self):
        ctx = _context()
        res = verify_improvement(ctx)
        self.assertGreaterEqual(len(res.evidence), 3)
        self.assertEqual(res.evidence, engine_module.build_evidence(ctx))

    def test_models_are_immutable(self):
        attempt = _attempt()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            attempt.problem_id = "X"  # type: ignore[misc]
        ctx = _context()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ctx.concept_id = "C1"  # type: ignore[misc]
        res = verify_improvement(ctx)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            res.outcome = VerificationOutcome.NOT_IMPROVED  # type: ignore[misc]

    def test_intervention_level_never_changes_verdict(self):
        base_kwargs = dict(original_outcome="PASS", transfer_outcome="PASS")
        res_a = verify_improvement(_context(level="hint-L1", **base_kwargs))
        res_b = verify_improvement(_context(level="worked-example", **base_kwargs))
        self.assertEqual(res_a.outcome, res_b.outcome)
        self.assertEqual(res_a.reason_code, res_b.reason_code)
        self.assertEqual(res_a.intervention_level, "hint-L1")
        self.assertEqual(res_b.intervention_level, "worked-example")

    def test_serialization_round_trips(self):
        ctx = _context()
        self.assertEqual(
            VerificationContext.from_dict(ctx.to_dict()), ctx
        )
        attempt = _attempt()
        self.assertEqual(
            VerificationAttempt.from_dict(attempt.to_dict()), attempt
        )
        res = verify_improvement(ctx)
        self.assertEqual(
            VerificationResult.from_dict(res.to_dict()), res
        )

    def test_normalization_is_case_and_space_tolerant(self):
        attempt = VerificationAttempt(
            problem_id="  PY-C3-001 ",
            concept_id=" c3 ",
            language_track=" Python ",
            outcome=" pass ",
        )
        self.assertEqual(attempt.concept_id, "C3")
        self.assertEqual(attempt.language_track, "python")
        self.assertEqual(attempt.outcome, ExecutionOutcome.PASS)


# ---------------------------------------------------------------------------
# Reason builder + wording contract
# ---------------------------------------------------------------------------
class ReasonBuilderTests(unittest.TestCase):
    def test_all_reason_templates_build(self):
        self.assertIn("INCOMPLETE", build_reason(
            "ORIGINAL_RETRY_MISSING", original_problem_id=ORIG))
        self.assertIn("NOT_IMPROVED", build_reason(
            "ORIGINAL_RETRY_FAILED", original_problem_id=ORIG,
            original_outcome="FAIL"))
        self.assertIn("INCOMPLETE", build_reason(
            "ORIGINAL_RETRY_PASSED_TRANSFER_MISSING",
            original_problem_id=ORIG, transfer_problem_id=TRANS))
        self.assertIn("SURFACE_FIX", build_reason(
            "ORIGINAL_RETRY_PASSED_TRANSFER_FAILED",
            original_problem_id=ORIG, transfer_problem_id=TRANS,
            transfer_outcome="FAIL"))
        text = build_reason(
            "ORIGINAL_AND_TRANSFER_PASSED",
            original_problem_id=ORIG, transfer_problem_id=TRANS)
        self.assertIn("VERIFIED_IMPROVED", text)

    def test_verified_reason_disclaims_mastery(self):
        res = verify_improvement(_context())
        lowered = res.reason.lower()
        self.assertIn("not", lowered)
        self.assertIn("mastery", lowered)
        self.assertNotIn("mastered the concept", lowered)

    def test_reason_builder_requires_branch_fields(self):
        with self.assertRaises(ValueError):
            build_reason("ORIGINAL_RETRY_FAILED", original_problem_id=ORIG)
        with self.assertRaises(ValueError):
            build_reason(
                "ORIGINAL_RETRY_PASSED_TRANSFER_FAILED",
                original_problem_id=ORIG, transfer_problem_id=TRANS)
        with self.assertRaises(ValueError):
            build_reason(
                "ORIGINAL_AND_TRANSFER_PASSED", original_problem_id=ORIG)


# ---------------------------------------------------------------------------
# Integration contract for Step 8 (read-only; learner_engine untouched)
# ---------------------------------------------------------------------------
class IntegrationContractTests(unittest.TestCase):
    def test_result_exposes_learner_engine_fields(self):
        res = verify_improvement(_context())
        for field in ("outcome", "concept_id", "target_misconception_id",
                      "original_passed", "transfer_passed", "evidence"):
            self.assertTrue(hasattr(res, field), field)
        self.assertEqual(res.concept_id, CONCEPT)
        self.assertEqual(res.target_misconception_id, TARGET)
        self.assertIsInstance(res.evidence, tuple)

    def test_to_learner_evidence_slice(self):
        res = verify_improvement(_context())
        payload = to_learner_evidence(res)
        self.assertEqual(payload["outcome"], "VERIFIED_IMPROVED")
        self.assertEqual(payload["concept_id"], CONCEPT)
        self.assertEqual(payload["target_misconception_id"], TARGET)
        self.assertTrue(payload["original_passed"])
        self.assertTrue(payload["transfer_passed"])
        self.assertEqual(list(payload["evidence"]), list(res.evidence))
        self.assertIn("reason_code", payload)
        self.assertIn("reason", payload)

    def test_to_learner_evidence_rejects_non_result(self):
        with self.assertRaises(TypeError):
            to_learner_evidence({"outcome": "VERIFIED_IMPROVED"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Static safety: pure package (no randomness/clock/IO/LLM/DB/mastery/ranking)
# ---------------------------------------------------------------------------
class StaticSafetyTests(unittest.TestCase):
    def test_package_sources_use_no_forbidden_mechanisms(self):
        import re

        pkg_dir = _ROOT / "packages" / "verification"
        sources = [
            pkg_dir / "__init__.py",
            pkg_dir / "models.py",
            pkg_dir / "reasons.py",
            pkg_dir / "engine.py",
        ]
        # Import-level bans: the package must never pull in IO / network /
        # DB / LLM / sibling-domain logic. Docstring *mentions* (e.g. "no
        # LLM calls", "mastery remains owned by Step 8") are allowed, so
        # only match real import statements.
        forbidden_imports = (
            "random", "datetime", "os", "socket", "requests", "httpx",
            "urllib", "sqlite", "sqlalchemy", "openai", "anthropic",
            "subprocess", "mastery", "adaptive", "learner_engine",
            "llm_client",
        )
        # Call-level bans: executable builtins / processes (word-boundary).
        forbidden_calls = ("open", "eval", "exec")
        import_re = re.compile(r"^\s*(?:import|from)\s+([^\s#]+)", re.MULTILINE)
        for path in sources:
            text = path.read_text(encoding="utf-8")
            for match in import_re.finditer(text):
                module = match.group(1).lower()
                for banned in forbidden_imports:
                    self.assertNotIn(
                        banned, module,
                        f"{path.name} must not import {banned!r}",
                    )
            for call in forbidden_calls:
                self.assertIsNone(
                    re.search(rf"\b{call}\s*\(", text),
                    f"{path.name} must not call {call}()",
                )


if __name__ == "__main__":
    unittest.main()
