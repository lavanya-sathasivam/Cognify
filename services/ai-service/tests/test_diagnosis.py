"""Unit tests for Step 7: AI Diagnosis (services/ai-service).

Covers: request/response models, EvidencePack-only prompt builder, LLM
client abstraction + env config, strict validator (hallucinated IDs
rejected), confidence/grounding gate, deterministic fallback classifier,
orchestrator with a MOCKED LLM (no network, no API key), FastAPI
endpoints, and static safety guarantees (no DB, no mastery, no hints,
no adaptive decisions, no hard-coded keys).

Run from repo root:
    python -m unittest discover -s services/ai-service/tests -t . -v

NOTE: ``services/ai-service`` is not an importable package name (hyphen),
so this file bootstraps ``sys.path`` with the repo root AND the service
dir, then imports ``app.*`` plus ``packages.evidence`` / ``packages.taxonomy``.
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

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import fallback as fallback_module  # noqa: E402
from app import gate as gate_module  # noqa: E402
from app import prompt as prompt_module  # noqa: E402
from app import service as service_module  # noqa: E402
from app import validator as validator_module  # noqa: E402
from app.config import get_llm_config  # noqa: E402
from app.fallback import fallback_diagnose  # noqa: E402
from app.gate import confidence_grounding_gate  # noqa: E402
from app.llm_client import (  # noqa: E402
    BaseLLMClient,
    LLMUnavailableError,
    MockLLMClient,
    OpenAICompatibleLLMClient,
    UnavailableLLMClient,
)
from app.main import create_app  # noqa: E402
from app.models import Diagnosis, DiagnosisResult  # noqa: E402
from app.prompt import build_diagnosis_prompt  # noqa: E402
from app.service import diagnose_pack  # noqa: E402
from app.validator import DiagnosisValidationError, validate_llm_diagnosis  # noqa: E402
from packages.evidence.examples import make_example_evidence_pack  # noqa: E402
from packages.evidence.models import EvidencePack  # noqa: E402

_APP_DIR = _SERVICE_DIR / "app"

_VALID_EXPLANATION = (
    "Loop bound excludes the final value, so the last even number is missed."
)


def _pack():
    return make_example_evidence_pack()


def _valid_payload(**overrides):
    base = {
        "concept_id": "C3",
        "misconception_id": "C3-M01",
        "confidence": 0.85,
        "explanation": _VALID_EXPLANATION,
        "evidence_refs": ["failed_test:P1", "expected_output", "actual_output"],
    }
    base.update(overrides)
    return copy.deepcopy(base)


def _mock_client_with(payload: dict) -> MockLLMClient:
    return MockLLMClient(text=json.dumps(payload), model="mock-test")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class DiagnosisModelTests(unittest.TestCase):
    def test_valid_diagnosis_normalizes_ids(self):
        d = Diagnosis(
            concept_id=" c3 ",
            misconception_id="c3-m01",
            confidence=0.7,
            explanation=_VALID_EXPLANATION,
            evidence_refs=["code", "stdout"],
        )
        self.assertEqual((d.concept_id, d.misconception_id), ("C3", "C3-M01"))
        self.assertEqual(d.to_dict()["confidence"], 0.7)

    def test_output_contains_required_fields(self):
        d = Diagnosis(
            concept_id="C3",
            misconception_id="C3-M01",
            confidence=0.5,
            explanation=_VALID_EXPLANATION,
            evidence_refs=["code"],
        )
        body = d.to_dict()
        for key in (
            "concept_id",
            "misconception_id",
            "confidence",
            "explanation",
            "evidence_refs",
        ):
            self.assertIn(key, body)

    def test_rejects_bad_confidence(self):
        good = {
            "concept_id": "C3",
            "misconception_id": "C3-M01",
            "explanation": _VALID_EXPLANATION,
            "evidence_refs": ["code"],
        }
        for bad in (-0.1, 1.5, float("nan") if False else 2.0, True, "0.9", None):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                Diagnosis(**{**good, "confidence": bad})
        # Boundaries are accepted.
        for ok in (0.0, 1.0, 0, 1):
            d = Diagnosis(**{**good, "confidence": ok})
            self.assertTrue(0.0 <= d.confidence <= 1.0)

    def test_rejects_non_concise_explanation(self):
        good = {
            "concept_id": "C3",
            "misconception_id": "C3-M01",
            "confidence": 0.5,
            "evidence_refs": ["code"],
        }
        with self.assertRaises(ValidationError):
            Diagnosis(**{**good, "explanation": "too short"})
        with self.assertRaises(ValidationError):
            Diagnosis(**{**good, "explanation": "   "})
        with self.assertRaises(ValidationError):
            Diagnosis(**{**good, "explanation": "x" * 501})

    def test_rejects_bad_evidence_refs(self):
        good = {
            "concept_id": "C3",
            "misconception_id": "C3-M01",
            "confidence": 0.5,
            "explanation": _VALID_EXPLANATION,
        }
        with self.assertRaises(ValidationError):
            Diagnosis(**{**good, "evidence_refs": []})
        with self.assertRaises(ValidationError):
            Diagnosis(**{**good, "evidence_refs": ["code", "code"]})
        with self.assertRaises(ValidationError):
            Diagnosis(**{**good, "evidence_refs": ["  "]})
        with self.assertRaises(ValidationError):
            Diagnosis(**{**good, "evidence_refs": ["x" * 201]})

    def test_rejects_extra_keys_strict(self):
        with self.assertRaises(ValidationError):
            Diagnosis(
                concept_id="C3",
                misconception_id="C3-M01",
                confidence=0.5,
                explanation=_VALID_EXPLANATION,
                evidence_refs=["code"],
                mastery=0.9,  # type: ignore[call-arg]
            )

    def test_result_source_is_llm_or_fallback(self):
        for source in ("llm", "fallback"):
            r = DiagnosisResult(
                concept_id="C3",
                misconception_id="C3-M01",
                confidence=0.5,
                explanation=_VALID_EXPLANATION,
                evidence_refs=["code"],
                source=source,  # type: ignore[arg-type]
            )
            self.assertEqual(r.source, source)
        with self.assertRaises(ValidationError):
            DiagnosisResult(
                concept_id="C3",
                misconception_id="C3-M01",
                confidence=0.5,
                explanation=_VALID_EXPLANATION,
                evidence_refs=["code"],
                source="adaptive",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Prompt builder (EvidencePack only)
# ---------------------------------------------------------------------------
class PromptBuilderTests(unittest.TestCase):
    def test_deterministic_for_same_pack(self):
        first = build_diagnosis_prompt(_pack())
        second = build_diagnosis_prompt(_pack())
        self.assertEqual(first, second)
        self.assertEqual(set(first), {"system", "user"})

    def test_accepts_dict_form_and_embeds_pack(self):
        pack = _pack()
        from_dict_prompt = build_diagnosis_prompt(pack.to_dict())
        from_obj_prompt = build_diagnosis_prompt(pack)
        self.assertEqual(from_dict_prompt, from_obj_prompt)
        self.assertIn(pack.concept_id, from_obj_prompt["user"])
        for cand in ("C3-M01", "C3-M04"):
            self.assertIn(cand, from_obj_prompt["user"])
        self.assertIn('"failed_test_id"', from_obj_prompt["user"])

    def test_system_constrains_ids_and_forbids_scope_creep(self):
        system = build_diagnosis_prompt(_pack())["system"]
        lowered = system.lower()
        self.assertIn("only one evidencepack", lowered)
        self.assertIn("no database", lowered)
        self.assertIn("must be exactly one of", lowered)
        self.assertIn("concept_id", system)
        self.assertIn("evidence_refs", system)
        for forbidden_task in ("mastery", "hint", "adaptive"):
            self.assertIn(forbidden_task, lowered)

    def test_prompt_takes_only_the_pack(self):
        import ast

        sig = inspect.signature(build_diagnosis_prompt)
        params = list(sig.parameters)
        self.assertEqual(params, ["pack"])
        # AST-level check: no DB/session imports or names in code
        # (docstring guard phrases like "diagnosis engine" are not code).
        tree = ast.parse(inspect.getsource(prompt_module))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                joined = " ".join(names).lower()
                for forbidden in ("sqlalchemy", "sqlite", "openai", "anthropic"):
                    self.assertNotIn(forbidden, joined)
            elif isinstance(node, ast.Name) and node.id in {
                "session", "engine", "create_engine", "sessionmaker",
            }:
                self.fail(f"prompt must not use DB name {node.id!r}")
            elif isinstance(node, ast.Attribute) and node.attr in {
                "environ", "getenv",
            }:
                self.fail("prompt must not read the environment")

    def test_user_prompt_is_valid_json_tail(self):
        prompt = build_diagnosis_prompt(_pack())
        tail = prompt["user"].split("EvidencePack JSON:\n", 1)[1]
        parsed = json.loads(tail)
        self.assertEqual(
            EvidencePack.from_dict(parsed), _pack(), "embedded pack must round-trip"
        )


# ---------------------------------------------------------------------------
# LLM client abstraction + env config
# ---------------------------------------------------------------------------
class LLMClientTests(unittest.TestCase):
    def test_mock_records_prompt_and_returns_text(self):
        client = MockLLMClient(text='{"a": 1}', model="mock-x")
        out = client.complete(system="sys", user="usr")
        self.assertEqual(out, '{"a": 1}')
        self.assertEqual(client.calls, [{"system": "sys", "user": "usr"}])
        self.assertEqual(client.model_name, "mock-x")
        self.assertIsInstance(client, BaseLLMClient)

    def test_mock_raises_canned_error(self):
        client = MockLLMClient(error=LLMUnavailableError("down"))
        with self.assertRaises(LLMUnavailableError):
            client.complete(system="s", user="u")

    def test_unavailable_always_raises(self):
        client = UnavailableLLMClient("no key")
        with self.assertRaises(LLMUnavailableError):
            client.complete(system="s", user="u")

    def test_openai_client_requires_key_and_model(self):
        with self.assertRaises(ValueError):
            OpenAICompatibleLLMClient(api_key="  ", model="gpt-4o-mini")
        with self.assertRaises(ValueError):
            OpenAICompatibleLLMClient(api_key="secret", model="  ")

    def test_env_config_defaults_and_errors(self):
        cfg = get_llm_config(env={})
        self.assertEqual(cfg.provider, "")
        self.assertFalse(cfg.enabled)
        cfg2 = get_llm_config(
            env={"LLM_PROVIDER": "openai", "LLM_API_KEY": "k", "LLM_MODEL": "m"}
        )
        self.assertTrue(cfg2.enabled)
        self.assertEqual((cfg2.api_key, cfg2.model), ("k", "m"))
        with self.assertRaises(ValueError):
            get_llm_config(env={"LLM_PROVIDER": "openai", "LLM_API_KEY": ""})
        with self.assertRaises(ValueError):
            get_llm_config(env={"LLM_PROVIDER": "anthropic", "LLM_API_KEY": "k"})
        with self.assertRaises(ValueError):
            get_llm_config(
                env={
                    "LLM_PROVIDER": "mock",
                    "LLM_TIMEOUT_SECONDS": "not-a-number",
                }
            )

    def test_no_hard_coded_api_keys(self):
        for name in ("config.py", "llm_client.py", "service.py", "main.py"):
            src = (_APP_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn("sk-", src, f"{name} must not hard-code API keys")
            self.assertNotIn("sk-proj-", src, f"{name} must not hard-code API keys")
        llm_src = (_APP_DIR / "llm_client.py").read_text(encoding="utf-8")
        self.assertIn("LLM_API_KEY", llm_src)  # key arrives via environment


# ---------------------------------------------------------------------------
# Validator (strict schema + grounding)
# ---------------------------------------------------------------------------
class ValidatorTests(unittest.TestCase):
    def test_accepts_valid_payload(self):
        d = validate_llm_diagnosis(_valid_payload(), _pack())
        self.assertEqual((d.concept_id, d.misconception_id), ("C3", "C3-M01"))
        self.assertTrue(0.0 <= d.confidence <= 1.0)
        self.assertEqual(len(d.evidence_refs), 3)

    def test_accepts_case_insensitive_ids_and_normalizes(self):
        payload = _valid_payload(concept_id=" c3 ", misconception_id="c3-m04")
        payload["evidence_refs"] = ["candidate:C3-M04", "failed_test:P1", "code"]
        d = validate_llm_diagnosis(payload, _pack())
        self.assertEqual((d.concept_id, d.misconception_id), ("C3", "C3-M04"))

    def test_rejects_non_dict_and_bad_shapes(self):
        for bad in ("[1,2]", '"str"', "[1]", "42", "null"):
            with self.assertRaises(DiagnosisValidationError, msg=bad):
                validate_llm_diagnosis(json.loads(bad), _pack())

    def test_rejects_missing_and_extra_keys(self):
        payload = _valid_payload()
        del payload["confidence"]
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(payload, _pack())
        payload2 = _valid_payload()
        payload2["mastery"] = 0.9
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(payload2, _pack())
        payload3 = _valid_payload()
        payload3["hint"] = "try range(n+1)"
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(payload3, _pack())

    def test_rejects_concept_mismatch(self):
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(concept_id="C2"), _pack())

    def test_rejects_hallucinated_misconception(self):
        # Same-concept but NOT a pack candidate (PY-C3-001 has M01+M04 only).
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(misconception_id="C3-M02"), _pack())
        # Another concept entirely.
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(misconception_id="C2-M01"), _pack())
        # Unknown ID.
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(misconception_id="C9-M99"), _pack())

    def test_rejects_bad_confidence_and_explanation(self):
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(confidence=1.5), _pack())
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(confidence=True), _pack())
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(confidence="high"), _pack())
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(explanation="short"), _pack())
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(explanation="x" * 501), _pack())

    def test_rejects_hallucinated_evidence_refs(self):
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(
                _valid_payload(evidence_refs=["failed_test:P99"]), _pack()
            )
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(
                _valid_payload(evidence_refs=["candidate:C3-M02"]), _pack()
            )
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(
                _valid_payload(evidence_refs=["database_row:42"]), _pack()
            )
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(_valid_payload(evidence_refs=[]), _pack())
        with self.assertRaises(DiagnosisValidationError):
            validate_llm_diagnosis(
                _valid_payload(evidence_refs=["code", "code"]), _pack()
            )

    def test_accepts_all_ref_kinds(self):
        payload = _valid_payload(
            evidence_refs=[
                "code",
                "execution_status",
                "stdout",
                "candidate:C3-M01",
                "history:C3-M01",
                "recurring:C3-M01",
            ]
        )
        d = validate_llm_diagnosis(payload, _pack())
        self.assertEqual(len(d.evidence_refs), 6)


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------
class GateTests(unittest.TestCase):
    def _diagnosis(self, **overrides):
        kwargs = {
            "concept_id": "C3",
            "misconception_id": "C3-M01",
            "confidence": 0.85,
            "explanation": _VALID_EXPLANATION,
            "evidence_refs": ["failed_test:P1", "expected_output", "actual_output"],
        }
        kwargs.update(overrides)
        return Diagnosis(**kwargs)

    def test_accepts_grounded_confident_diagnosis(self):
        accepted, reason = confidence_grounding_gate(self._diagnosis(), _pack())
        self.assertTrue(accepted)
        self.assertIn("accepted", reason)

    def test_rejects_low_confidence(self):
        accepted, reason = confidence_grounding_gate(
            self._diagnosis(confidence=0.2), _pack()
        )
        self.assertFalse(accepted)
        self.assertIn("below", reason)

    def test_rejects_ungrounded_refs_for_failed_pack(self):
        # Only taxonomy labels, no observable failure link.
        diag = self._diagnosis(evidence_refs=["candidate:C3-M01"])
        accepted, reason = confidence_grounding_gate(diag, _pack())
        self.assertFalse(accepted)
        self.assertIn("grounding", reason.lower())

    def test_passed_pack_needs_no_failure_link(self):
        from packages.evidence.builder import build_evidence_pack
        from packages.evidence.models import ConceptStateSnapshot, LearnerSnapshot
        from packages.problem_schema.examples import EXAMPLE_PYTHON_PROBLEM

        passed_exec = {
            "status": "PASSED",
            "language": "python",
            "execution_time_ms": 20,
            "stdout": "6",
            "stderr": "",
            "tests": [
                {
                    "test_id": "P1",
                    "passed": True,
                    "input": "5",
                    "expected_output": "6",
                    "actual_output": "6",
                    "stdout": "6",
                    "stderr": "",
                    "exit_code": 0,
                    "timed_out": False,
                    "time_ms": 9,
                }
            ],
            "passed_count": 1,
            "failed_count": 0,
            "failed_test_id": None,
            "expected_output": None,
            "actual_output": None,
        }
        snap = LearnerSnapshot(
            user_id=1,
            journey_id=2,
            language_track="python",
            concept_state=ConceptStateSnapshot(concept_id="C3"),
        )
        passed_pack = build_evidence_pack(
            code="print(6)\n",
            problem=EXAMPLE_PYTHON_PROBLEM,
            execution_result=passed_exec,
            learner_snapshot=snap,
        )
        diag = Diagnosis(
            concept_id="C3",
            misconception_id="C3-M01",
            confidence=0.6,
            explanation=_VALID_EXPLANATION,
            evidence_refs=["execution_status", "code"],
        )
        accepted, _ = confidence_grounding_gate(diag, passed_pack)
        self.assertTrue(accepted)


# ---------------------------------------------------------------------------
# Fallback (deterministic)
# ---------------------------------------------------------------------------
class FallbackTests(unittest.TestCase):
    def test_deterministic_and_grounded(self):
        first = fallback_diagnose(_pack())
        second = fallback_diagnose(_pack())
        self.assertEqual(first, second)
        self.assertEqual(first.concept_id, "C3")
        self.assertIn(
            first.misconception_id, ["C3-M01", "C3-M04"], "must be a candidate"
        )
        self.assertTrue(0.0 <= first.confidence <= 1.0)
        self.assertTrue(10 <= len(first.explanation) <= 500)
        self.assertGreaterEqual(len(first.evidence_refs), 1)

    def test_prefers_recurring_and_frequent_candidate(self):
        # Example pack: C3-M01 is recurring with 3 occurrences vs C3-M04 with 1.
        result = fallback_diagnose(_pack())
        self.assertEqual(result.misconception_id, "C3-M01")
        self.assertIn("failed_test:P1", result.evidence_refs)

    def test_accepts_dict_pack_and_matches_object(self):
        pack = _pack()
        self.assertEqual(fallback_diagnose(pack.to_dict()), fallback_diagnose(pack))

    def test_confidence_capped_for_passed_execution(self):
        from packages.evidence.builder import build_evidence_pack
        from packages.evidence.models import ConceptStateSnapshot, LearnerSnapshot
        from packages.problem_schema.examples import EXAMPLE_PYTHON_PROBLEM

        passed_exec = {
            "status": "PASSED",
            "language": "python",
            "execution_time_ms": 20,
            "stdout": "6",
            "stderr": "",
            "tests": [
                {
                    "test_id": "P1",
                    "passed": True,
                    "input": "5",
                    "expected_output": "6",
                    "actual_output": "6",
                    "stdout": "6",
                    "stderr": "",
                    "exit_code": 0,
                    "timed_out": False,
                    "time_ms": 9,
                }
            ],
            "passed_count": 1,
            "failed_count": 0,
            "failed_test_id": None,
            "expected_output": None,
            "actual_output": None,
        }
        snap = LearnerSnapshot(
            user_id=1,
            journey_id=2,
            language_track="python",
            concept_state=ConceptStateSnapshot(concept_id="C3"),
        )
        passed_pack = build_evidence_pack(
            code="print(6)\n",
            problem=EXAMPLE_PYTHON_PROBLEM,
            execution_result=passed_exec,
            learner_snapshot=snap,
        )
        result = fallback_diagnose(passed_pack)
        self.assertLessEqual(result.confidence, 0.40)
        self.assertIn(result.misconception_id, ["C3-M01", "C3-M04"])


# ---------------------------------------------------------------------------
# Service orchestration (mocked LLM)
# ---------------------------------------------------------------------------
class ServiceTests(unittest.TestCase):
    def test_valid_llm_response_returns_llm_source(self):
        client = _mock_client_with(_valid_payload())
        result = diagnose_pack(_pack(), client)
        self.assertEqual(result.source, "llm")
        self.assertEqual((result.concept_id, result.misconception_id), ("C3", "C3-M01"))
        self.assertAlmostEqual(result.confidence, 0.85)
        # The LLM only saw the prompt built from the pack.
        self.assertEqual(len(client.calls), 1)
        self.assertIn("C3", client.calls[0]["user"])

    def test_tolerates_markdown_fences(self):
        fenced = "```json\n" + json.dumps(_valid_payload()) + "\n```"
        result = diagnose_pack(_pack(), MockLLMClient(text=fenced))
        self.assertEqual(result.source, "llm")

    def test_hallucinated_id_falls_back(self):
        client = _mock_client_with(_valid_payload(misconception_id="C3-M02"))
        result = diagnose_pack(_pack(), client)
        self.assertEqual(result.source, "fallback")
        self.assertIn(result.misconception_id, ["C3-M01", "C3-M04"])

    def test_wrong_concept_falls_back(self):
        client = _mock_client_with(_valid_payload(concept_id="C2"))
        result = diagnose_pack(_pack(), client)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.concept_id, "C3")

    def test_malformed_json_falls_back(self):
        result = diagnose_pack(_pack(), MockLLMClient(text="not json {"))
        self.assertEqual(result.source, "fallback")

    def test_llm_error_falls_back(self):
        client = MockLLMClient(error=LLMUnavailableError("outage"))
        result = diagnose_pack(_pack(), client)
        self.assertEqual(result.source, "fallback")

    def test_none_client_falls_back(self):
        result = diagnose_pack(_pack(), None)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.concept_id, "C3")

    def test_low_confidence_falls_back(self):
        client = _mock_client_with(_valid_payload(confidence=0.1))
        result = diagnose_pack(_pack(), client)
        self.assertEqual(result.source, "fallback")

    def test_ungrounded_llm_response_falls_back(self):
        payload = _valid_payload(evidence_refs=["candidate:C3-M01"])
        result = diagnose_pack(_pack(), _mock_client_with(payload))
        self.assertEqual(result.source, "fallback")

    def test_extra_keys_fall_back(self):
        payload = _valid_payload()
        payload["mastery"] = 0.9
        result = diagnose_pack(_pack(), _mock_client_with(payload))
        self.assertEqual(result.source, "fallback")

    def test_service_signature_only_sees_pack_and_client(self):
        import ast

        sig = inspect.signature(diagnose_pack)
        self.assertEqual(list(sig.parameters)[:2], ["pack", "client"])
        # AST-level: docstring guard phrases ("never calculates mastery",
        # "never generates hints", "no adaptive decisions") are prose, not
        # logic — so inspect code names, not raw docstring text.
        tree = ast.parse(inspect.getsource(service_module))
        code_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                code_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                code_names.add(node.attr)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for mod in mods:
                    code_names.add(mod.split(".")[0].lower())
        for forbidden in ("session", "engine", "create_engine", "sessionmaker",
                          "roadmap", "sqlalchemy"):
            self.assertNotIn(forbidden, code_names,
                             f"service must not handle {forbidden}")
        # No mastery/hint/adaptive *logic*: no such function defs or calls.
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    any(k in node.name.lower() for k in ("mastery", "hint", "adaptive")):
                # diagnose_pack / _parse_llm_json are the only allowed defs.
                if node.name not in ("diagnose_pack", "_parse_llm_json"):
                    self.fail(f"service must not define {node.name!r}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and any(k in node.func.id.lower() for k in ("mastery", "hint", "adaptive")):
                self.fail(f"service must not call {node.func.id!r}")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class DiagnosisApiTests(unittest.TestCase):
    def test_health(self):
        client = TestClient(create_app(llm_client=MockLLMClient(text="{}")))
        body = client.get("/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "ai-service")

    def test_diagnose_with_valid_llm(self):
        app_client = TestClient(
            create_app(llm_client=_mock_client_with(_valid_payload()))
        )
        resp = app_client.post(
            "/diagnose", json={"evidence_pack": _pack().to_dict()}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        for key in (
            "concept_id",
            "misconception_id",
            "confidence",
            "explanation",
            "evidence_refs",
            "source",
        ):
            self.assertIn(key, body)
        self.assertEqual(body["source"], "llm")
        self.assertEqual(body["concept_id"], "C3")
        self.assertEqual(body["misconception_id"], "C3-M01")
        self.assertTrue(0.0 <= body["confidence"] <= 1.0)

    def test_diagnose_falls_back_when_llm_down(self):
        app_client = TestClient(
            create_app(llm_client=UnavailableLLMClient("no key"))
        )
        resp = app_client.post(
            "/diagnose", json={"evidence_pack": _pack().to_dict()}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["concept_id"], "C3")
        self.assertIn(body["misconception_id"], ["C3-M01", "C3-M04"])

    def test_diagnose_rejects_malformed_pack(self):
        app_client = TestClient(create_app(llm_client=MockLLMClient(text="{}")))
        bad = _pack().to_dict()
        bad["concept_id"] = "C99"
        resp = app_client.post("/diagnose", json={"evidence_pack": bad})
        self.assertEqual(resp.status_code, 422)
        resp2 = app_client.post("/diagnose", json={"evidence_pack": {"x": 1}})
        self.assertEqual(resp2.status_code, 422)

    def test_default_app_is_fallback_only_without_env(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            app_client = TestClient(create_app())
            resp = app_client.post(
                "/diagnose", json={"evidence_pack": _pack().to_dict()}
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["source"], "fallback")


# ---------------------------------------------------------------------------
# Static safety guarantees
# ---------------------------------------------------------------------------
class DiagnosisSafetyTests(unittest.TestCase):
    def _sources(self) -> dict[str, str]:
        return {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(_APP_DIR.glob("*.py"))
        }

    def test_no_database_access(self):
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
                    for forbidden in ("sqlalchemy",):
                        self.assertNotIn(forbidden, joined, f"{name}: no DB imports")
        for name, src in self._sources().items():
            for token in ("create_engine", "sessionmaker", "DATABASE_URL"):
                self.assertNotIn(token, src, f"{name} must not touch the database")

    def test_no_mastery_hint_or_adaptive_logic(self):
        import ast

        # AST-level: docstring guard phrases ("never calculates mastery",
        # "never generates hints", "no adaptive/roadmap decisions") are prose
        # and live in docstrings (Constant nodes) — only code identifiers count.
        for name, src in self._sources().items():
            tree = ast.parse(src, filename=name)
            code_ids: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    code_ids.add(node.id.lower())
                elif isinstance(node, ast.Attribute):
                    code_ids.add(node.attr.lower())
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef)):
                    code_ids.add(node.name.lower())
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    for mod in mods:
                        code_ids.add(mod.split(".")[0].lower())
            for cid in code_ids:
                for forbidden in ("mastery", "roadmap", "adaptive", "hint"):
                    self.assertNotIn(forbidden, cid,
                                     f"{name}: forbidden logic {forbidden!r} in {cid!r}")
            for forbidden in ("update_concept_state", "increment_counter",
                              "set_recurring_flag", "generate_hint"):
                self.assertNotIn(forbidden, code_ids,
                                 f"{name}: forbidden {forbidden}")
            self.assertNotIn("sqlalchemy", code_ids, f"{name}: no DB imports")

    def test_no_execution_primitives_or_hard_coded_secrets(self):
        import ast

        for name, src in self._sources().items():
            tree = ast.parse(src, filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in {"eval", "exec", "compile"}:
                    self.fail(f"{name}: forbidden call to {node.func.id}()")
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for prefix in ("sk-", "sk-proj-"):
                        self.assertNotIn(
                            prefix, node.value, f"{name}: hard-coded secret?"
                        )


if __name__ == "__main__":
    unittest.main()
