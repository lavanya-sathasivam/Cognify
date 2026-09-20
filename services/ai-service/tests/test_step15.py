"""Unit tests for Step 15: Evidence-Grounded Diagnosis Quality + Intervention.

Adds a small deterministic rule layer BEFORE the generic fallback
(``app.rules``) plus a structured intervention mapping (``app.interventions``)
without rewriting anything from Steps 6-14:

- Evidence Pack architecture, mastery formula, adaptive ranking,
  verification semantics, and the deterministic fallback classifier are
  untouched (asserted by the regression suites + the no-duplication tests
  below).
- Hierarchy under test: strong rule -> LLM (when available) -> fallback.
  Rule hits are deterministic non-LLM output and keep the existing
  ``"fallback"`` source vocabulary, so every Step 7 / Step 14 assertion
  still holds; rule firing is observable via the ``"Rule <ID>:"``
  explanation prefix and by comparing against ``fallback_diagnose``.

Run from repo root:
    python -m unittest discover -s services/ai-service/tests -t . -v

NOTE: ``services/ai-service`` is not an importable package name (hyphen),
so this file bootstraps ``sys.path`` with the repo root AND the service
dir, then imports ``app.*`` plus ``packages.*`` (same pattern as
``test_diagnosis.py``).
"""
from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path

# -- sys.path bootstrap (repo root + service dir) ---------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
_SERVICE_DIR = _ROOT / "services" / "ai-service"
for _p in (str(_ROOT), str(_SERVICE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app import rules as rules_module  # noqa: E402
from app.fallback import fallback_diagnose  # noqa: E402
from app.gate import MIN_ACCEPT_CONFIDENCE, confidence_grounding_gate  # noqa: E402
from app.interventions import (  # noqa: E402
    LEVEL_NAMES,
    Intervention,
    build_intervention,
    level_for_history,
)
from app.llm_client import MockLLMClient, UnavailableLLMClient  # noqa: E402
from app.models import Diagnosis  # noqa: E402
from app.rules import (  # noqa: E402
    RULES,
    RULE_CONFIDENCE,
    RULE_C3_RANGE_BOUNDARY_EXCLUSION,
    RULE_C3_RANGE_EXCLUSIVITY,
    try_rule_diagnosis,
)
from app.service import diagnose_pack  # noqa: E402
from app.validator import validate_llm_diagnosis  # noqa: E402
from packages.evidence.examples import make_example_evidence_pack  # noqa: E402
from packages.evidence.models import EvidencePack  # noqa: E402
from packages.taxonomy import get_misconception  # noqa: E402

_APP_DIR = _SERVICE_DIR / "app"

# Step 14 failure pattern: terminal index never visited.
_R1_CODE = (
    "def count_divisible(nums, k):\n"
    '    """Return how many numbers in nums are divisible by k."""\n'
    "    count = 0\n"
    "    for i in range(len(nums) - 1):\n"
    "        if nums[i] % k == 0:\n"
    "            count += 1\n"
    "    return count\n"
)

# Range-exclusivity pattern: unadjusted stop drops the terminal value.
_R2_CODE = (
    "def sum_to_n(n):\n"
    '    """Return the sum 1 + 2 + ... + n inclusive."""\n'
    "    total = 0\n"
    "    for i in range(1, n):\n"
    "        total += i\n"
    "    return total\n"
)


def _candidate_entry(mid: str) -> dict:
    info = get_misconception(mid)
    return {
        "misconception_id": info.id,
        "concept_id": info.concept_id,
        "name": info.name,
        "typical_signal": info.typical_signal,
    }


def _craft_pack(
    *,
    code: str,
    candidates: "list[str]",
    failures: "list[tuple[str, str, str, str]]",
    passed_count: int,
    history: "list[dict] | None" = None,
    flags: "list[dict] | None" = None,
) -> EvidencePack:
    """Build a valid EvidencePack by mutating the example pack's dict form."""
    data = make_example_evidence_pack().to_dict()
    data["code"] = code
    data["misconception_candidates"] = [_candidate_entry(m) for m in candidates]
    data["misconception_history"] = list(history or [])
    data["recurring_flags"] = list(flags or [])
    failed = [
        {
            "test_id": tid,
            "input": inp,
            "expected_output": exp,
            "actual_output": act,
            "stdout": act,
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "time_ms": 5,
        }
        for (tid, inp, exp, act) in failures
    ]
    data["failed_tests"] = failed
    data["failed_count"] = len(failed)
    data["failed_test_id"] = failed[0]["test_id"]
    data["expected_output"] = failed[0]["expected_output"]
    data["actual_output"] = failed[0]["actual_output"]
    data["stdout"] = failed[0]["stdout"]
    data["stderr"] = ""
    data["execution_status"] = "FAILED"
    data["passed_count"] = passed_count
    return EvidencePack.from_dict(data)


def _r1_pack(**overrides) -> EvidencePack:
    kwargs = {
        "code": _R1_CODE,
        "candidates": ["C3-M01", "C3-M04"],
        "failures": [
            ("P2", "4 3\n3 6 7 9\n", "3", "2"),
            ("H2", "6 2\n2 4 6 8 10 12\n", "6", "5"),
            ("H3", "3 1\n7 8 9\n", "3", "2"),
        ],
        "passed_count": 2,
    }
    kwargs.update(overrides)
    return _craft_pack(**kwargs)


def _r2_pack(**overrides) -> EvidencePack:
    kwargs = {
        "code": _R2_CODE,
        # C3-M01 sorts before C3-M05: the generic fallback tie-break would
        # pick M01, so a rule hit for M05 proves evidence beats lexicography.
        "candidates": ["C3-M01", "C3-M05"],
        "failures": [
            ("P1", "5\n", "15", "10"),
            ("P2", "1\n", "1", "0"),
            ("H1", "10\n", "55", "45"),
        ],
        "passed_count": 0,
    }
    kwargs.update(overrides)
    return _craft_pack(**kwargs)


def _history_entry(mid: str, count: int) -> dict:
    return {
        "misconception_id": mid,
        "concept_id": "C3",
        "occurrence_count": count,
        "active": True,
        "last_seen_at": None,
    }


def _flag_entry(mid: str, recurring: bool) -> dict:
    return {
        "misconception_id": mid,
        "concept_id": "C3",
        "is_recurring": recurring,
        "reason": "test reason" if recurring else None,
    }


def _valid_llm_payload(**overrides) -> dict:
    base = {
        "concept_id": "C3",
        "misconception_id": "C3-M01",
        "confidence": 0.85,
        "explanation": (
            "Loop bound excludes the final value, so the last even number is missed."
        ),
        "evidence_refs": ["failed_test:P1", "expected_output", "actual_output"],
    }
    base.update(overrides)
    return copy.deepcopy(base)


# ---------------------------------------------------------------------------
# Rules: Step 14 pattern + range exclusivity
# ---------------------------------------------------------------------------
class RuleMatchTests(unittest.TestCase):
    def test_r1_fires_on_step14_boundary_pattern(self):
        hit = try_rule_diagnosis(_r1_pack())
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.misconception_id, "C3-M01")
        self.assertEqual(hit.concept_id, "C3")
        self.assertIn(RULE_C3_RANGE_BOUNDARY_EXCLUSION, hit.explanation)

    def test_r2_fires_on_range_exclusivity_pattern(self):
        hit = try_rule_diagnosis(_r2_pack())
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.misconception_id, "C3-M05")
        self.assertEqual(hit.concept_id, "C3")
        self.assertIn(RULE_C3_RANGE_EXCLUSIVITY, hit.explanation)

    def test_rule_layer_declares_exactly_two_c3_rules(self):
        self.assertEqual(len(RULES), 2)
        by_id = {r.rule_id: r for r in RULES}
        self.assertEqual(
            set(by_id),
            {RULE_C3_RANGE_BOUNDARY_EXCLUSION, RULE_C3_RANGE_EXCLUSIVITY},
        )
        self.assertEqual(by_id[RULE_C3_RANGE_BOUNDARY_EXCLUSION].target_misconception_id, "C3-M01")
        self.assertEqual(by_id[RULE_C3_RANGE_EXCLUSIVITY].target_misconception_id, "C3-M05")
        for rule in RULES:
            # Every rule target must be a real taxonomy ID (never invented).
            get_misconception(rule.target_misconception_id)

    def test_rule_confidence_meets_acceptance_threshold(self):
        self.assertGreaterEqual(RULE_CONFIDENCE, MIN_ACCEPT_CONFIDENCE)
        self.assertLess(RULE_CONFIDENCE, 1.0)
        for pack in (_r1_pack(), _r2_pack()):
            hit = try_rule_diagnosis(pack)
            assert hit is not None
            self.assertAlmostEqual(hit.confidence, RULE_CONFIDENCE)
            accepted, _reason = confidence_grounding_gate(hit, pack)
            self.assertTrue(accepted)

    def test_rule_evidence_refs_are_valid_and_grounded(self):
        for pack in (_r1_pack(), _r2_pack()):
            hit = try_rule_diagnosis(pack)
            assert hit is not None
            # The existing validator accepts every rule-produced diagnosis.
            validated = validate_llm_diagnosis(hit.to_dict(), pack)
            self.assertEqual(validated, hit)
            decisive = pack.failed_tests[0].test_id
            self.assertIn(f"failed_test:{decisive}", hit.evidence_refs)
            self.assertIn("code", hit.evidence_refs)

    def test_rule_output_matches_pack_concept_and_candidates(self):
        for pack in (_r1_pack(), _r2_pack()):
            hit = try_rule_diagnosis(pack)
            assert hit is not None
            self.assertEqual(hit.concept_id, pack.concept_id)
            candidate_ids = {c.misconception_id for c in pack.misconception_candidates}
            self.assertIn(hit.misconception_id, candidate_ids)

    def test_dict_pack_form_matches_object_form(self):
        pack = _r1_pack()
        self.assertEqual(try_rule_diagnosis(pack.to_dict()), try_rule_diagnosis(pack))


# ---------------------------------------------------------------------------
# Rules abstain when evidence is insufficient (never force a diagnosis)
# ---------------------------------------------------------------------------
class RuleAbstentionTests(unittest.TestCase):
    def test_example_pack_abstains(self):
        self.assertIsNone(try_rule_diagnosis(make_example_evidence_pack()))

    def test_code_pattern_without_output_signal_abstains(self):
        pack = _r1_pack(
            failures=[("P2", "4 3\n3 6 7 9\n", "3", "0")],
            passed_count=2,
        )
        self.assertIsNone(try_rule_diagnosis(pack))

    def test_output_signal_without_code_pattern_abstains(self):
        code = (
            "def count_divisible(nums, k):\n"
            "    count = 0\n"
            "    for x in nums:\n"
            "        if x % k == 0:\n"
            "            count += 1\n"
            "    return count\n"
        )
        pack = _r1_pack(code=code)
        self.assertIsNone(try_rule_diagnosis(pack))

    def test_missing_candidate_abstains(self):
        pack = _r1_pack(candidates=["C3-M04"])
        self.assertIsNone(try_rule_diagnosis(pack))
        pack2 = _r2_pack(candidates=["C3-M01"])
        self.assertIsNone(try_rule_diagnosis(pack2))

    def test_nonuniform_failures_abstain(self):
        pack = _r1_pack(
            failures=[
                ("P2", "4 3\n3 6 7 9\n", "3", "2"),
                ("H2", "6 2\n2 4 6 8 10 12\n", "6", "0"),
            ],
            passed_count=2,
        )
        self.assertIsNone(try_rule_diagnosis(pack))

    def test_no_passing_test_abstains_for_r1(self):
        pack = _r1_pack(passed_count=0)
        self.assertIsNone(try_rule_diagnosis(pack))

    def test_passed_execution_abstains(self):
        data = make_example_evidence_pack().to_dict()
        data["code"] = _R1_CODE
        data["failed_tests"] = []
        data["failed_count"] = 0
        data["failed_test_id"] = None
        data["expected_output"] = None
        data["actual_output"] = None
        data["execution_status"] = "PASSED"
        data["passed_count"] = 2
        pack = EvidencePack.from_dict(data)
        self.assertIsNone(try_rule_diagnosis(pack))

    def test_error_status_abstains(self):
        data = _r1_pack().to_dict()
        data["execution_status"] = "RUNTIME_ERROR"
        pack = EvidencePack.from_dict(data)
        self.assertIsNone(try_rule_diagnosis(pack))

    def test_unparseable_code_abstains(self):
        pack = _r1_pack(code="def broken(:\n    not python {{{\n")
        # Pack validation accepts any code string; the rule must abstain.
        self.assertIsNone(try_rule_diagnosis(pack))

    def test_never_matches_on_problem_id(self):
        # Same Step 14 evidence shape but a different problem id must still
        # fire (evidence-driven), while evidence removal must not.
        data = _r1_pack().to_dict()
        data["problem_id"] = "PY-C3-OTHER"
        pack = EvidencePack.from_dict(data)
        hit = try_rule_diagnosis(pack)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.misconception_id, "C3-M01")


# ---------------------------------------------------------------------------
# Hierarchy: rule -> LLM -> fallback
# ---------------------------------------------------------------------------
class HierarchyTests(unittest.TestCase):
    def test_llm_path_still_works_when_rules_abstain(self):
        pack = make_example_evidence_pack()
        client = MockLLMClient(text=json.dumps(_valid_llm_payload()), model="mock")
        result = diagnose_pack(pack, client)
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.misconception_id, "C3-M01")
        self.assertEqual(len(client.calls), 1)

    def test_strong_rule_bypasses_llm_even_when_available(self):
        pack = _r2_pack()
        payload = _valid_llm_payload(misconception_id="C3-M01")
        client = MockLLMClient(text=json.dumps(payload), model="mock")
        result = diagnose_pack(pack, client)
        self.assertEqual(result.misconception_id, "C3-M05")
        self.assertIn(RULE_C3_RANGE_EXCLUSIVITY, result.explanation)
        self.assertEqual(client.calls, [])

    def test_fallback_still_works_when_llm_unavailable_and_rules_abstain(self):
        pack = make_example_evidence_pack()
        result = diagnose_pack(pack, UnavailableLLMClient("no key"))
        self.assertEqual(result.source, "fallback")
        expected = fallback_diagnose(pack)
        self.assertEqual(result.misconception_id, expected.misconception_id)
        self.assertEqual(result.confidence, expected.confidence)

    def test_none_client_with_strong_evidence_returns_rule_diagnosis(self):
        pack = _r1_pack()
        result = diagnose_pack(pack, None)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.misconception_id, "C3-M01")
        self.assertIn(RULE_C3_RANGE_BOUNDARY_EXCLUSION, result.explanation)
        self.assertAlmostEqual(result.confidence, RULE_CONFIDENCE)

    def test_rule_beats_generic_fallback_when_strongly_grounded(self):
        pack = _r2_pack()
        generic = fallback_diagnose(pack)
        # Generic tie-break picks the lexicographically smallest candidate.
        self.assertEqual(generic.misconception_id, "C3-M01")
        result = diagnose_pack(pack, None)
        self.assertEqual(result.misconception_id, "C3-M05")
        self.assertNotEqual(result.misconception_id, generic.misconception_id)

    def test_no_lexicographic_tie_break_when_strong_rule_applies(self):
        pack = _r2_pack()
        candidates = sorted(c.misconception_id for c in pack.misconception_candidates)
        self.assertLess(candidates[0], "C3-M05")  # M01 sorts first
        result = diagnose_pack(pack, None)
        self.assertEqual(result.misconception_id, "C3-M05")

    def test_dict_pack_rules_apply(self):
        result = diagnose_pack(_r1_pack().to_dict(), None)
        self.assertEqual(result.misconception_id, "C3-M01")
        self.assertIn(RULE_C3_RANGE_BOUNDARY_EXCLUSION, result.explanation)

    def test_repeated_pack_gives_identical_rule_diagnosis(self):
        first = diagnose_pack(_r1_pack(), None)
        second = diagnose_pack(_r1_pack(), None)
        self.assertEqual(first, second)
        self.assertEqual(try_rule_diagnosis(_r2_pack()), try_rule_diagnosis(_r2_pack()))

    def test_service_signature_still_sees_pack_and_client(self):
        params = list(inspect.signature(diagnose_pack).parameters)
        self.assertEqual(params[:2], ["pack", "client"])


# ---------------------------------------------------------------------------
# Intervention mapping
# ---------------------------------------------------------------------------
class InterventionTests(unittest.TestCase):
    def test_r1_intervention_maps_to_diagnosed_misconception(self):
        pack = _r1_pack()
        hit = try_rule_diagnosis(pack)
        assert hit is not None
        action = build_intervention(hit, pack)
        self.assertEqual(action.misconception_id, "C3-M01")
        self.assertEqual(action.intervention_type, "BOUNDARY_CHECK")
        self.assertEqual(action.intervention_level, "L1")
        self.assertTrue(action.target_skill.strip())
        self.assertIn("P2", action.explanation + action.recommended_action)

    def test_r2_intervention_maps_to_diagnosed_misconception(self):
        pack = _r2_pack()
        hit = try_rule_diagnosis(pack)
        assert hit is not None
        action = build_intervention(hit, pack)
        self.assertEqual(action.misconception_id, "C3-M05")
        self.assertEqual(action.intervention_type, "TRACE_LOOP")
        self.assertEqual(action.intervention_level, "L1")

    def test_intervention_object_is_structured_and_actionable(self):
        pack = _r1_pack()
        hit = try_rule_diagnosis(pack)
        assert hit is not None
        body = build_intervention(hit, pack).to_dict()
        self.assertEqual(
            set(body),
            {
                "misconception_id",
                "intervention_level",
                "intervention_type",
                "target_skill",
                "explanation",
                "recommended_action",
            },
        )
        self.assertIn(body["intervention_level"], ("L1", "L2", "L3", "L4"))
        self.assertIn(
            body["intervention_type"],
            ("MICRO_LESSON", "TARGETED_HINT", "BOUNDARY_CHECK", "TRACE_LOOP", "REMEDIAL_PROBLEM"),
        )
        for key in ("target_skill", "explanation", "recommended_action"):
            self.assertGreaterEqual(len(body[key]), 10)
        self.assertEqual(LEVEL_NAMES["L1"], "NUDGE")
        self.assertEqual(LEVEL_NAMES["L2"], "MICRO_LESSON")
        self.assertEqual(LEVEL_NAMES["L3"], "SCAFFOLD")
        self.assertEqual(LEVEL_NAMES["L4"], "RETEACH")

    def test_level_escalation_uses_existing_history_only(self):
        pack = _r1_pack()
        hit = try_rule_diagnosis(pack)
        assert hit is not None
        # Fresh learner: no escalation from the current failure alone.
        self.assertEqual(build_intervention(hit, pack).intervention_level, "L1")
        # Seen once before: L2.
        seen = _r1_pack(history=[_history_entry("C3-M01", 1)])
        self.assertEqual(build_intervention(hit, seen).intervention_level, "L2")
        # Recurring: L3 even at low counts.
        recurring = _r1_pack(
            history=[_history_entry("C3-M01", 2)],
            flags=[_flag_entry("C3-M01", True)],
        )
        self.assertEqual(build_intervention(hit, recurring).intervention_level, "L3")
        # Recurring with 3+ occurrences: L4.
        reteach = _r1_pack(
            history=[_history_entry("C3-M01", 3)],
            flags=[_flag_entry("C3-M01", True), _flag_entry("C3-M04", False)],
        )
        self.assertEqual(build_intervention(hit, reteach).intervention_level, "L4")
        # History for OTHER candidates does not escalate this diagnosis.
        other = _r1_pack(
            history=[_history_entry("C3-M04", 5)],
            flags=[_flag_entry("C3-M04", True)],
        )
        self.assertEqual(build_intervention(hit, other).intervention_level, "L1")

    def test_level_for_history_table(self):
        self.assertEqual(
            level_for_history(occurrence_count=0, is_recurring=False), "L1"
        )
        self.assertEqual(
            level_for_history(occurrence_count=1, is_recurring=False), "L2"
        )
        self.assertEqual(
            level_for_history(occurrence_count=2, is_recurring=True), "L3"
        )
        self.assertEqual(
            level_for_history(occurrence_count=3, is_recurring=True), "L4"
        )

    def test_rejects_ungrounded_misconception(self):
        pack = _r1_pack()
        bogus = Diagnosis(
            concept_id="C3",
            misconception_id="C3-M05",
            confidence=0.8,
            explanation="A sufficiently long explanation for the test case.",
            evidence_refs=["code"],
        )
        with self.assertRaises(ValueError):
            build_intervention(bogus, pack)

    def test_rejects_concept_mismatch(self):
        pack = _r1_pack()
        mismatched = Diagnosis(
            concept_id="C2",
            misconception_id="C3-M01",
            confidence=0.8,
            explanation="A sufficiently long explanation for the test case.",
            evidence_refs=["code"],
        )
        with self.assertRaises(ValueError):
            build_intervention(mismatched, pack)

    def test_intervention_is_deterministic(self):
        pack = _r1_pack()
        hit = try_rule_diagnosis(pack)
        assert hit is not None
        self.assertEqual(
            build_intervention(hit, pack).to_dict(),
            build_intervention(hit, pack).to_dict(),
        )

    def test_intervention_accepts_dict_forms(self):
        pack = _r1_pack()
        hit = try_rule_diagnosis(pack)
        assert hit is not None
        action = build_intervention(hit.to_dict(), pack.to_dict())
        self.assertEqual(action.misconception_id, "C3-M01")


# ---------------------------------------------------------------------------
# Purity: no DB writes, no learner mutation, no adaptive duplication
# ---------------------------------------------------------------------------
class PurityTests(unittest.TestCase):
    def _sources(self) -> dict[str, str]:
        return {
            name: (_APP_DIR / name).read_text(encoding="utf-8")
            for name in ("rules.py", "interventions.py", "service.py")
        }

    def test_no_database_access_in_new_modules(self):
        import ast

        for name, src in self._sources().items():
            tree = ast.parse(src, filename=name)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    joined = " ".join(names).lower()
                    self.assertNotIn("sqlalchemy", joined, f"{name}: no DB imports")
            for token in ("create_engine", "sessionmaker", "DATABASE_URL"):
                self.assertNotIn(token, src, f"{name} must not touch the database")

    def test_no_adaptive_mastery_verification_or_evidence_duplication(self):
        import ast

        duplicated = {
            # mastery formula internals (packages.mastery owns these)
            "compute_mastery_update",
            "severity_for_status",
            "mastery_band",
            "compute_trend",
            # learner-model internals (core-backend owns these)
            "record_attempt",
            "snapshot_for_evidence",
            "get_concept_view",
            "get_misconception_view",
            # adaptive policy internals (packages.adaptive owns these)
            "evaluate_concept",
            "evaluate_all",
            "recommend_next_actions",
            "rank_recommendations",
            "rank_key",
            "urgency_bonus",
            # verification internals (packages.verification owns these)
            "verify_improvement",
            "build_reason",
            "build_evidence",
            # evidence builder (packages.evidence owns this)
            "build_evidence_pack",
            # generic fallback internals (fallback.py owns these)
            "fallback_diagnose",
        }
        for name in ("rules.py", "interventions.py"):
            src = self._sources()[name]
            tree = ast.parse(src, filename=name)
            called: set[str] = set()
            defined: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defined.add(node.name)
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name):
                        called.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        called.add(func.attr)
            hits = (called | defined) & duplicated
            self.assertEqual(hits, set(), f"{name} duplicates logic: {hits}")

    def test_no_learner_model_mutation(self):
        pack = _r1_pack()
        before = pack.to_dict()
        hit = try_rule_diagnosis(pack)
        assert hit is not None
        build_intervention(hit, pack)
        diagnose_pack(pack, None)
        self.assertEqual(pack.to_dict(), before)
        self.assertIsNone(pack.confirmed_misconception_id)

    def test_no_execution_primitives_or_secrets(self):
        import ast

        for name, src in self._sources().items():
            tree = ast.parse(src, filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in {"eval", "exec", "compile"}:
                    self.fail(f"{name}: forbidden call to {node.func.id}()")
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for prefix in ("sk-", "sk-proj-"):
                        self.assertNotIn(prefix, node.value, f"{name}: hard-coded secret?")


# ---------------------------------------------------------------------------
# Step 14 journey still works end-to-end (now evidence-grounded)
# ---------------------------------------------------------------------------
class Step14JourneyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys as _sys

        if str(_ROOT) not in _sys.path:
            _sys.path.insert(0, str(_ROOT))
        from packages.problem_bank import journey as journey_mod  # noqa: E402

        cls.journey_mod = journey_mod
        cls.result = journey_mod.run_learning_journey()
        cls.body = cls.result.to_dict()

    def test_journey_diagnosis_is_rule_grounded(self):
        diagnosis = self.body["diagnosis"]
        self.assertEqual(diagnosis["concept_id"], "C3")
        self.assertEqual(diagnosis["misconception_id"], "C3-M01")
        self.assertIn(RULE_C3_RANGE_BOUNDARY_EXCLUSION, diagnosis["explanation"])
        self.assertGreaterEqual(diagnosis["confidence"], MIN_ACCEPT_CONFIDENCE)
        self.assertEqual(diagnosis["source"], "fallback")
        self.assertIn(
            f"failed_test:{self.body['evidence_pack']['failed_test_id']}",
            diagnosis["evidence_refs"],
        )

    def test_journey_still_verifies_improvement(self):
        self.assertEqual(self.result.verification_outcome, "VERIFIED_IMPROVED")
        self.assertTrue(self.result.learner_updated)
        self.assertEqual(
            self.body["verification"]["target_misconception_id"],
            self.body["diagnosis"]["misconception_id"],
        )

    def test_journey_intervention_builds_from_rule_diagnosis(self):
        pack = EvidencePack.from_dict(self.body["evidence_pack"])
        hit = try_rule_diagnosis(pack)
        self.assertIsNotNone(hit)
        action = build_intervention(self.body["diagnosis"], pack)
        self.assertEqual(
            action.misconception_id, self.body["diagnosis"]["misconception_id"]
        )
        self.assertEqual(action.intervention_level, "L1")

    def test_journey_remains_deterministic(self):
        again = self.journey_mod.run_learning_journey()
        self.assertEqual(again.to_dict(), self.result.to_dict())


if __name__ == "__main__":
    unittest.main()
