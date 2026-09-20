"""Unit tests for Step 12: Problem Bank + Execution Integration.

Vertical slice for ONE Python problem (PY-C3-COUNT-DIV, concept C3):

    Problem Bank (JSON loader)
        -> execution-service evaluator + sandbox runners (Step 5, reused)
        -> EvidencePack builder (Step 6, reused)
        -> AI diagnosis service with fallback (Step 7, reused)
        -> verification engine + closed-loop planning (Steps 10/11, reused)

All execution is DETERMINISTIC and scripted through the EXISTING
FakeSandboxRunner (same mechanism as the execution-service unit tests):
no Docker, no host interpreter, no wall-clock timing. The student code
strings below are realistic submissions; the sandbox scripts encode what
the Docker sandbox would return for them.

Service access goes ONLY through ``packages.problem_bank.pipeline``,
which loads the existing service code under collision-free aliases
(``cognify_exec_app`` / ``cognify_ai_app`` / ``cognify_core_app``), so
this file bootstraps just the repo root (never the hyphenated service
dirs — importing two ``app.*`` packages directly would collide).

Run from repo root:
    python -m unittest discover -s packages/problem_bank/tests -t . -v
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

# -- sys.path bootstrap (repo root only; pipeline alias-loads services) ----
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.evidence.models import EvidencePack  # noqa: E402
from packages.problem_bank import loader as bank_loader  # noqa: E402
from packages.problem_bank import pipeline as pipe  # noqa: E402
from packages.problem_schema.examples import EXAMPLE_PYTHON_PROBLEM  # noqa: E402
from packages.problem_schema.models import Problem  # noqa: E402
from packages.verification import (  # noqa: E402
    VerificationContext,
    verify_improvement,
)

PROBLEM_ID = "PY-C3-COUNT-DIV"

# ---------------------------------------------------------------------------
# Realistic student submissions (data only; executed solely inside the
# existing sandbox abstraction via scripted fakes, never on the host).
# ---------------------------------------------------------------------------
CORRECT_CODE = (
    "def count_divisible(nums, k):\n"
    "    count = 0\n"
    "    for x in nums:\n"
    "        if x % k == 0:\n"
    "            count += 1\n"
    "    return count\n"
    "\n"
    "\n"
    "def main():\n"
    "    import sys\n"
    "    data = sys.stdin.read().strip().split()\n"
    "    if not data:\n"
    "        return\n"
    "    n = int(data[0])\n"
    "    k = int(data[1])\n"
    "    nums = list(map(int, data[2:2 + n]))\n"
    "    print(count_divisible(nums, k))\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)

# Off-by-one / boundary mistake: skips the last element (C3-M01 signal).
OFF_BY_ONE_CODE = (
    "def count_divisible(nums, k):\n"
    "    count = 0\n"
    "    for i in range(len(nums) - 1):\n"
    "        if nums[i] % k == 0:\n"
    "            count += 1\n"
    "    return count\n"
    "\n"
    "\n"
    "def main():\n"
    "    import sys\n"
    "    data = sys.stdin.read().strip().split()\n"
    "    if not data:\n"
    "        return\n"
    "    n = int(data[0])\n"
    "    k = int(data[1])\n"
    "    nums = list(map(int, data[2:2 + n]))\n"
    "    print(count_divisible(nums, k))\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)

SYNTAX_ERROR_CODE = (
    "def count_divisible(nums, k)\n"
    "    count = 0\n"
    "    for x in nums:\n"
    "        if x % k == 0:\n"
    "            count += 1\n"
    "    return count\n"
)

RUNTIME_ERROR_CODE = (
    "def count_divisible(nums, k):\n"
    "    count = 0\n"
    "    for x in nums:\n"
    "        if x % k == 0:\n"
    "            count += 1 / 0\n"
    "    return count\n"
    "\n"
    "\n"
    "def main():\n"
    "    import sys\n"
    "    data = sys.stdin.read().strip().split()\n"
    "    if not data:\n"
    "        return\n"
    "    n = int(data[0])\n"
    "    k = int(data[1])\n"
    "    nums = list(map(int, data[2:2 + n]))\n"
    "    print(count_divisible(nums, k))\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)

INFINITE_LOOP_CODE = (
    "def count_divisible(nums, k):\n"
    "    count = 0\n"
    "    i = 0\n"
    "    while i < len(nums):\n"
    "        if nums[i] % k == 0:\n"
    "            count += 1\n"
    "    return count\n"
)

_SYNTAX_STDERR = (
    '  File "/workspace/solution.py", line 1\n'
    "    def count_divisible(nums, k)\n"
    "                                    ^\n"
    "SyntaxError: expected ':'\n"
)
_RUNTIME_STDERR = (
    '  File "/workspace/solution.py", line 5, in count_divisible\n'
    "    count += 1 / 0\n"
    "ZeroDivisionError: division by zero\n"
)


def _load_problem() -> Problem:
    return bank_loader.load_problem(PROBLEM_ID)


def _reference_count(stdin_data: str) -> str:
    """Pure re-implementation of the spec (validates test DATA, not strings).

    Mirrors the canonical algorithm without executing any submission
    string: parses ``n k`` + ``n`` ints, counts ``x % k == 0``.
    """
    parts = stdin_data.strip().split()
    n, k = int(parts[0]), int(parts[1])
    nums = list(map(int, parts[2:2 + n]))
    count = 0
    for x in nums:
        if x % k == 0:
            count += 1
    return str(count)


def _correct_script(problem: Problem) -> dict:
    return pipe.script_for_outputs(problem, lambda stdin, expected: "correct")


def _off_by_one_script(problem: Problem) -> dict:
    def _handler(stdin, expected):
        # Deterministic wrong answer: one less (or 1 when expected is 0).
        wrong = str(int(expected) - 1) if int(expected) > 0 else "1"
        return wrong + "\n"

    return pipe.script_for_outputs(problem, _handler)


def _error_script(problem: Problem, stderr: str) -> dict:
    def _handler(stdin, expected):
        return {
            "stdout": "",
            "stderr": stderr,
            "exit_code": 1,
            "timed_out": False,
        }

    return pipe.script_for_outputs(problem, _handler)


def _timeout_script(problem: Problem) -> dict:
    def _handler(stdin, expected):
        return {
            "stdout": "",
            "stderr": "TIMEOUT: exceeded 5.0s wall-clock limit.",
            "exit_code": -1,
            "timed_out": True,
            "time_ms": 5000,
        }

    return pipe.script_for_outputs(problem, _handler, time_ms=5000)


def _run(problem: Problem, code: str, script: dict):
    runner = pipe.make_scripted_python_runner(script)
    return pipe.execute_problem(problem, code, runner)


# ---------------------------------------------------------------------------
# 1-2: loader
# ---------------------------------------------------------------------------
class ProblemLoadTests(unittest.TestCase):
    def test_problem_loads_successfully(self):
        problem = _load_problem()
        self.assertEqual(problem.problem_id, PROBLEM_ID)
        self.assertEqual(problem.language, "python")
        self.assertEqual(problem.concept_id, "C3")
        self.assertEqual(problem.difficulty, 2)
        self.assertEqual(problem.variant_role, "canonical")
        self.assertEqual(problem.isomorphic_group_id, "ISO-C3-COUNT-DIV")
        self.assertEqual(problem.misconception_ids, ("C3-M01", "C3-M04"))
        self.assertTrue(problem.title.strip())
        self.assertTrue(problem.description.strip())
        self.assertTrue(problem.starter_code.strip())
        self.assertTrue(problem.input_format.strip())
        self.assertTrue(problem.output_format.strip())
        self.assertGreaterEqual(len(problem.constraints), 1)
        self.assertEqual(len(problem.public_tests), 2)
        self.assertEqual(len(problem.hidden_tests), 3)
        self.assertEqual(len(problem.test_ids()), 5)
        self.assertEqual(len(set(problem.test_ids())), 5)
        # Round-trip through JSON preserves equality.
        as_dict = problem.to_dict()
        self.assertEqual(Problem.from_dict(copy.deepcopy(as_dict)), problem)

    def test_reference_logic_matches_all_expected_outputs(self):
        problem = _load_problem()
        for case in problem.all_tests():
            self.assertEqual(
                _reference_count(case.input),
                case.expected_output,
                f"test {case.id} data disagrees with the spec",
            )

    def test_problem_differs_from_schema_examples(self):
        problem = _load_problem()
        self.assertNotEqual(problem.problem_id, EXAMPLE_PYTHON_PROBLEM.problem_id)
        self.assertEqual(EXAMPLE_PYTHON_PROBLEM.problem_id, "PY-C3-001")
        # Examples still validate (Steps 6-11 fixtures untouched).
        self.assertEqual(
            Problem.from_dict(EXAMPLE_PYTHON_PROBLEM.to_dict()),
            EXAMPLE_PYTHON_PROBLEM,
        )

    def test_invalid_problem_is_rejected(self):
        good = _load_problem().to_dict()
        bad_concept = dict(good, concept_id="C9")
        with self.assertRaises(ValueError):
            Problem.from_dict(bad_concept)
        bad_lang = dict(good, language="ruby")
        with self.assertRaises(ValueError):
            Problem.from_dict(bad_lang)
        bad_role = dict(good, variant_role="isomorphic")
        with self.assertRaises(ValueError):
            Problem.from_dict(bad_role)
        bad_tests = dict(
            good,
            public_tests=[],
        )
        with self.assertRaises(ValueError):
            Problem.from_dict(bad_tests)
        dup = dict(
            good,
            public_tests=[
                {"id": "P1", "input": "a", "expected_output": "a"},
                {"id": "P1", "input": "b", "expected_output": "b"},
            ],
        )
        with self.assertRaises(ValueError):
            Problem.from_dict(dup)
        wrong_misc = dict(good, misconception_ids=["C2-M01"])
        with self.assertRaises(ValueError):
            Problem.from_dict(wrong_misc)
        missing = dict(good)
        del missing["title"]
        with self.assertRaises(ValueError):
            Problem.from_dict(missing)

    def test_loader_rejects_bad_files_and_unknown_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.json"
            broken.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(ValueError):
                bank_loader.load_problem_file(broken)
            non_object = Path(tmp) / "list.json"
            non_object.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(ValueError):
                bank_loader.load_problem_file(non_object)
            bad_schema = Path(tmp) / "bad.json"
            good = _load_problem().to_dict()
            good["concept_id"] = "C99"
            bad_schema.write_text(json.dumps(good), encoding="utf-8")
            with self.assertRaises(ValueError):
                bank_loader.load_problem_file(bad_schema)
            with self.assertRaises(ValueError):
                bank_loader.load_problem_file(Path(tmp) / "missing.json")
        with self.assertRaises(ValueError):
            bank_loader.load_problem("NO-SUCH-PROBLEM")
        with self.assertRaises(ValueError):
            bank_loader.load_problem("   ")
        with self.assertRaises(TypeError):
            bank_loader.load_problem(123)  # type: ignore[arg-type]

    def test_bank_lists_exactly_one_problem(self):
        ids = bank_loader.list_problem_ids()
        self.assertEqual(ids, [PROBLEM_ID])
        all_problems = bank_loader.load_all_problems()
        self.assertEqual(sorted(all_problems), [PROBLEM_ID])
        self.assertEqual(all_problems[PROBLEM_ID].concept_id, "C3")


# ---------------------------------------------------------------------------
# 3-7: execution (scripted sandbox; deterministic, no wall-clock)
# ---------------------------------------------------------------------------
class ExecutionTests(unittest.TestCase):
    def test_correct_submission_passes(self):
        problem = _load_problem()
        result = _run(problem, CORRECT_CODE, _correct_script(problem))
        self.assertEqual(pipe.execution_status_str(result), "PASSED")
        data = pipe.result_to_dict(result)
        self.assertEqual(data["language"], "python")
        self.assertEqual((data["passed_count"], data["failed_count"]), (5, 0))
        self.assertIsNone(data["failed_test_id"])
        self.assertTrue(all(t["passed"] for t in data["tests"]))

    def test_off_by_one_fails_with_useful_evidence(self):
        problem = _load_problem()
        result = _run(problem, OFF_BY_ONE_CODE, _off_by_one_script(problem))
        self.assertEqual(pipe.execution_status_str(result), "FAILED")
        data = pipe.result_to_dict(result)
        self.assertEqual(data["failed_count"], 5)
        self.assertEqual(data["passed_count"], 0)
        self.assertEqual(data["failed_test_id"], "P1")
        self.assertEqual(data["expected_output"], "2")
        self.assertEqual(data["actual_output"], "1\n")
        first = data["tests"][0]
        self.assertFalse(first["passed"])
        self.assertEqual(first["exit_code"], 0)
        self.assertFalse(first["timed_out"])

    def test_syntax_error_handled_deterministically(self):
        # Python has no build step (existing semantics): a SyntaxError
        # surfaces as RUNTIME_ERROR with a non-zero exit, deterministically.
        problem = _load_problem()
        result = _run(
            problem, SYNTAX_ERROR_CODE, _error_script(problem, _SYNTAX_STDERR)
        )
        self.assertEqual(pipe.execution_status_str(result), "RUNTIME_ERROR")
        data = pipe.result_to_dict(result)
        self.assertIn("SyntaxError", data["stderr"])
        self.assertGreater(data["failed_count"], 0)
        repeat = _run(
            problem, SYNTAX_ERROR_CODE, _error_script(problem, _SYNTAX_STDERR)
        )
        self.assertEqual(pipe.result_to_dict(repeat), pipe.result_to_dict(result))

    def test_runtime_error_handled(self):
        problem = _load_problem()
        result = _run(
            problem, RUNTIME_ERROR_CODE, _error_script(problem, _RUNTIME_STDERR)
        )
        self.assertEqual(pipe.execution_status_str(result), "RUNTIME_ERROR")
        data = pipe.result_to_dict(result)
        self.assertIn("ZeroDivisionError", data["stderr"])
        self.assertEqual(data["failed_test_id"], "P1")

    def test_timeout_handled_without_wall_clock(self):
        problem = _load_problem()
        result = _run(problem, INFINITE_LOOP_CODE, _timeout_script(problem))
        self.assertEqual(pipe.execution_status_str(result), "TIMEOUT")
        data = pipe.result_to_dict(result)
        self.assertTrue(any(t["timed_out"] for t in data["tests"]))
        self.assertIn("TIMEOUT", data["stderr"])

    def test_deterministic_repeated_execution(self):
        problem = _load_problem()
        first = pipe.result_to_dict(
            _run(problem, CORRECT_CODE, _correct_script(problem))
        )
        second = pipe.result_to_dict(
            _run(problem, CORRECT_CODE, _correct_script(problem))
        )
        self.assertEqual(first, second)
        failing_first = pipe.result_to_dict(
            _run(problem, OFF_BY_ONE_CODE, _off_by_one_script(problem))
        )
        failing_second = pipe.result_to_dict(
            _run(problem, OFF_BY_ONE_CODE, _off_by_one_script(problem))
        )
        self.assertEqual(failing_first, failing_second)

    def test_rejects_runner_language_mismatch(self):
        problem = _load_problem()

        class _Javaish:
            language = "java"

            def run_single(self, code, stdin_data, timeout_seconds):
                raise AssertionError("must not run")

        with self.assertRaises(ValueError):
            pipe.execute_problem(problem, CORRECT_CODE, _Javaish())


# ---------------------------------------------------------------------------
# 8-12: evidence, diagnosis, language/concept, hidden redaction
# ---------------------------------------------------------------------------
class EvidenceDiagnosisTests(unittest.TestCase):
    def _failed_pack(self):
        problem = _load_problem()
        result = _run(problem, OFF_BY_ONE_CODE, _off_by_one_script(problem))
        pack = pipe.build_pack_for_submission(OFF_BY_ONE_CODE, problem, result)
        return problem, result, pack

    def test_execution_maps_correctly_to_evidence_pack(self):
        problem, result, pack = self._failed_pack()
        self.assertIsInstance(pack, EvidencePack)
        self.assertEqual(pack.problem_id, PROBLEM_ID)
        self.assertEqual(pack.language, "python")
        self.assertEqual(pack.concept_id, "C3")
        self.assertEqual(
            pack.execution_status, pipe.execution_status_str(result)
        )
        data = pipe.result_to_dict(result)
        self.assertEqual(pack.passed_count, data["passed_count"])
        self.assertEqual(pack.failed_count, data["failed_count"])
        self.assertEqual(pack.failed_test_id, data["failed_test_id"])
        self.assertEqual(pack.expected_output, data["expected_output"])
        self.assertEqual(pack.actual_output, data["actual_output"])
        self.assertEqual(len(pack.failed_tests), data["failed_count"])
        self.assertEqual(
            [c.misconception_id for c in pack.misconception_candidates],
            ["C3-M01", "C3-M04"],
        )
        self.assertEqual(pack.evidence_kind, "observed")
        self.assertIsNone(pack.confirmed_misconception_id)
        self.assertEqual(pack.inference_status, "pending-diagnosis")
        # Round-trip preserves equality (deterministic).
        self.assertEqual(EvidencePack.from_dict(pack.to_dict()), pack)

    def test_evidence_reaches_existing_diagnosis_service(self):
        _, _, pack = self._failed_pack()
        result = pipe.diagnose_evidence(pack, None)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.concept_id, "C3")
        self.assertIn(result.misconception_id, ["C3-M01", "C3-M04"])

    def test_evidence_reaches_diagnosis_http_api(self):
        _, _, pack = self._failed_pack()
        llm_mod = pipe.ai_llm_client_module()
        status, body = pipe.diagnose_via_http(
            pack, llm_mod.UnavailableLLMClient("no key in tests")
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["concept_id"], "C3")
        self.assertIn(body["misconception_id"], ["C3-M01", "C3-M04"])

    def test_mock_llm_path_still_grounded(self):
        import json as _json

        _, _, pack = self._failed_pack()
        llm_mod = pipe.ai_llm_client_module()
        payload = {
            "concept_id": "C3",
            "misconception_id": "C3-M01",
            "confidence": 0.85,
            "explanation": (
                "Loop skips the final element, so the last divisible "
                "number is missed."
            ),
            "evidence_refs": [
                "failed_test:P1",
                "expected_output",
                "actual_output",
            ],
        }
        client = llm_mod.MockLLMClient(text=_json.dumps(payload))
        result = pipe.diagnose_evidence(pack, client)
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.misconception_id, "C3-M01")

    def test_language_remains_python(self):
        problem, result, pack = self._failed_pack()
        self.assertEqual(problem.language, "python")
        self.assertEqual(pipe.result_to_dict(result)["language"], "python")
        self.assertEqual(pack.language, "python")
        self.assertEqual(pack.learner.language_track, "python")
        diagnosis = pipe.diagnose_evidence(pack, None)
        self.assertEqual(pack.language, "python")
        self.assertEqual(diagnosis.concept_id, "C3")

    def test_problem_concept_remains_c3(self):
        problem, _, pack = self._failed_pack()
        self.assertEqual(problem.concept_id, "C3")
        self.assertEqual(pack.concept_id, "C3")
        diagnosis = pipe.diagnose_evidence(pack, None)
        self.assertEqual(diagnosis.concept_id, "C3")

    def test_hidden_expected_outputs_not_exposed_to_students(self):
        problem = _load_problem()
        public_inputs = {t.input for t in problem.public_tests}

        def _handler(stdin, expected):
            if stdin in public_inputs:
                return "correct"
            return "999\n"  # hidden tests fail; decisive failure is H1

        result = _run(problem, OFF_BY_ONE_CODE, pipe.script_for_outputs(problem, _handler))
        internal = pipe.result_to_dict(result)
        self.assertEqual(internal["failed_test_id"], "H1")
        self.assertEqual(internal["expected_output"], "0")
        view = pipe.to_student_view(problem, result)
        hidden_ids = {t.id for t in problem.hidden_tests}
        for entry in view["tests"]:
            if entry["test_id"] in hidden_ids:
                self.assertTrue(entry["is_hidden"])
                self.assertIsNone(
                    entry["expected_output"],
                    f"hidden test {entry['test_id']} must not expose expected",
                )
            else:
                self.assertFalse(entry["is_hidden"])
                self.assertIsNotNone(entry["expected_output"])
        # Decisive hidden failure: top-level expected is redacted, but the
        # internal result (for EvidencePack) still carries it.
        self.assertIsNone(view["expected_output"])
        self.assertEqual(internal["expected_output"], "0")
        self.assertEqual(view["problem_id"], PROBLEM_ID)
        dumped = json.dumps(view)
        self.assertNotIn('"expected_output": "0"', dumped)


# ---------------------------------------------------------------------------
# Closed loop (honest: verification built ONLY from actual executions;
# only pure planning is exercised — no DB writes, nothing fabricated).
# ---------------------------------------------------------------------------
class ClosedLoopPlanningTests(unittest.TestCase):
    def test_failed_execution_plans_not_improved_without_fabrication(self):
        problem = _load_problem()
        result = _run(problem, OFF_BY_ONE_CODE, _off_by_one_script(problem))
        pack = pipe.build_pack_for_submission(OFF_BY_ONE_CODE, problem, result)
        diagnosis = pipe.diagnose_evidence(pack, None)
        attempt = pipe.attempt_from_execution(
            problem, result, misconception_id=diagnosis.misconception_id
        )
        self.assertEqual(attempt.outcome.value, "FAIL")
        context = VerificationContext(
            original_problem_id=problem.problem_id,
            transfer_problem_id=None,
            concept_id=problem.concept_id,
            language_track=problem.language,
            target_misconception_id=diagnosis.misconception_id,
            original_retry=attempt,
            transfer=None,
            isomorphic_group_id=problem.isomorphic_group_id,
        )
        vresult = verify_improvement(context)
        self.assertEqual(vresult.outcome.value, "NOT_IMPROVED")
        closed_loop = pipe.closed_loop_module()
        loop_ctx = closed_loop.ClosedLoopContext(
            user_id=1,
            journey_id=1,
            language_track="python",
            concept_id="C3",
            problem_id=problem.problem_id,
            transfer_problem_id=None,
            verification_result=vresult,
        )
        plans = pipe.plan_records_for_context(loop_ctx)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.kind, "original_retry")
        self.assertFalse(plan.passed)
        # The recorded status derives from the ACTUAL execution status.
        self.assertEqual(
            plan.execution_status, pipe.execution_status_str(result)
        )
        self.assertEqual(
            plan.diagnosed_misconception_id, diagnosis.misconception_id
        )
        self.assertEqual(plan.isomorphic_group_id, problem.isomorphic_group_id)

    def test_passed_execution_without_transfer_stays_incomplete(self):
        problem = _load_problem()
        result = _run(problem, CORRECT_CODE, _correct_script(problem))
        attempt = pipe.attempt_from_execution(problem, result)
        self.assertEqual(attempt.outcome.value, "PASS")
        context = VerificationContext(
            original_problem_id=problem.problem_id,
            transfer_problem_id=None,
            concept_id=problem.concept_id,
            language_track=problem.language,
            target_misconception_id=None,
            original_retry=attempt,
            transfer=None,
            isomorphic_group_id=problem.isomorphic_group_id,
        )
        vresult = verify_improvement(context)
        self.assertEqual(vresult.outcome.value, "INCOMPLETE")
        closed_loop = pipe.closed_loop_module()
        loop_ctx = closed_loop.ClosedLoopContext(
            user_id=1,
            journey_id=1,
            language_track="python",
            concept_id="C3",
            problem_id=problem.problem_id,
            transfer_problem_id=None,
            verification_result=vresult,
        )
        # INCOMPLETE plans zero mutations: nothing is manufactured.
        self.assertEqual(pipe.plan_records_for_context(loop_ctx), ())

    def test_status_mapping_covers_all_terminal_statuses(self):
        self.assertEqual(
            pipe.verification_outcome_for("PASSED").value, "PASS"
        )
        self.assertEqual(
            pipe.verification_outcome_for("FAILED").value, "FAIL"
        )
        for status in ("COMPILE_ERROR", "RUNTIME_ERROR", "TIMEOUT"):
            self.assertEqual(
                pipe.verification_outcome_for(status).value, status
            )
        with self.assertRaises(ValueError):
            pipe.verification_outcome_for("GUESSSED")


# ---------------------------------------------------------------------------
# Security: new code adds no execution/network/secret surface; existing
# sandbox protections are preserved (checked behaviorally, not by prose).
# ---------------------------------------------------------------------------
class Step12SafetyTests(unittest.TestCase):
    def _sources(self) -> dict[str, str]:
        base = _ROOT / "packages" / "problem_bank"
        return {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(base.glob("*.py"))
        }

    def test_no_new_execution_or_secret_primitives(self):
        # AST-level check (mirrors the existing execution-service
        # SecurityTests): docstring guard phrases such as "no subprocess"
        # are prose, not code — only real code identifiers count.
        import ast

        for name, src in self._sources().items():
            if name == "__init__.py":
                continue
            tree = ast.parse(src, filename=name)
            code_ids: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(
                    node.func, ast.Name
                ):
                    self.assertNotIn(
                        node.func.id,
                        {"eval", "exec", "compile"},
                        f"{name}: forbidden call to {node.func.id}()",
                    )
                    code_ids.add(node.func.id.lower())
                elif isinstance(node, ast.Name):
                    code_ids.add(node.id.lower())
                elif isinstance(node, ast.Attribute):
                    code_ids.add(node.attr.lower())
                    self.assertNotIn(
                        node.attr,
                        {"environ", "getenv", "getenvb"},
                        f"{name}: host env access is forbidden",
                    )
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    for mod in mods:
                        code_ids.add(mod.split(".")[0].lower())
                for keyword in getattr(node, "keywords", []):
                    if keyword.arg == "shell" and isinstance(
                        keyword.value, ast.Constant
                    ):
                        self.assertNotEqual(
                            keyword.value.value,
                            True,
                            f"{name}: shell=True is forbidden",
                        )
            for forbidden in (
                "subprocess",
                "socket",
                "sqlalchemy",
                "openai",
                "anthropic",
                "httpx",
                "requests",
            ):
                self.assertNotIn(
                    forbidden, code_ids, f"{name}: forbidden import {forbidden!r}"
                )
            for token in ("os.system", "DATABASE_URL", "sk-proj-"):
                self.assertNotIn(token, src, f"{name} must not contain {token!r}")

    def test_existing_sandbox_protections_preserved(self):
        mods = pipe.execution_modules()
        sandbox = mods["sandbox"]
        runner = mods["sandbox"].DockerSandboxRunner(image="python:3.11-slim") \
            if hasattr(mods["sandbox"], "DockerSandboxRunner") else None
        self.assertIsNotNone(runner)
        assert runner is not None
        argv = runner.build_command("/tmp/x", "cognify-exec-abc")
        for flag in ("--network", "none", "--memory", "--cpus", "--pids-limit"):
            self.assertIn(flag, argv)
        for forbidden in ("-e", "--env", "--env-file"):
            self.assertNotIn(forbidden, argv)
        self.assertTrue(
            sandbox.SandboxUnavailableError is not None
        )


if __name__ == "__main__":
    unittest.main()
