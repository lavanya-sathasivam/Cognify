"""Unit tests for packages.problem_schema (stdlib unittest, no third-party deps).

No problem code is ever executed here — only schema validation.
"""
from __future__ import annotations

import dataclasses
import unittest

from packages.problem_schema.examples import (
    EXAMPLE_BY_ID,
    EXAMPLE_JAVA_PROBLEM,
    EXAMPLE_PROBLEMS,
    EXAMPLE_PYTHON_PROBLEM,
    EXAMPLE_TRANSFER_PROBLEM,
)
from packages.problem_schema.models import (
    VALID_VARIANT_ROLES,
    Problem,
    TestCase,
    is_valid_difficulty,
    is_valid_variant_role,
)


def make_valid_kwargs(**overrides):
    base = {
        "problem_id": "TEST-001",
        "concept_id": "C1",
        "language": "python",
        "difficulty": 2,
        "title": "Test problem",
        "description": "A minimal valid problem.",
        "constraints": ["1 <= n <= 10"],
        "starter_code": "def f(n):\n    raise NotImplementedError\n",
        "input_format": "An integer n.",
        "output_format": "An integer.",
        "public_tests": [TestCase(id="P1", input="1", expected_output="1")],
        "hidden_tests": [TestCase(id="H1", input="2", expected_output="2")],
        "isomorphic_group_id": "ISO-TEST",
        "variant_role": "canonical",
        "misconception_ids": ["C1-M01"],
    }
    base.update(overrides)
    return base


class TestCaseModelTests(unittest.TestCase):
    def test_valid(self):
        t = TestCase(id="P1", input="5", expected_output="6")
        self.assertEqual(t.id, "P1")
        self.assertEqual(t.input, "5")
        self.assertEqual(t.expected_output, "6")

    def test_empty_input_allowed(self):
        t = TestCase(id="T1", input="", expected_output="0")
        self.assertEqual(t.input, "")

    def test_id_must_be_non_empty(self):
        for bad in ["", "   "]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                TestCase(id=bad, input="1", expected_output="1")

    def test_id_pattern(self):
        with self.assertRaises(ValueError):
            TestCase(id="has space", input="1", expected_output="1")
        with self.assertRaises(ValueError):
            TestCase(id="-lead", input="1", expected_output="1")

    def test_id_types_rejected(self):
        for bad in [None, 123, ["P1"]]:
            with self.assertRaises(TypeError, msg=repr(bad)):
                TestCase(id=bad, input="1", expected_output="1")

    def test_input_expected_must_be_str(self):
        with self.assertRaises(TypeError):
            TestCase(id="P1", input=123, expected_output="1")
        with self.assertRaises(TypeError):
            TestCase(id="P1", input="1", expected_output=None)

    def test_frozen(self):
        t = TestCase(id="P1", input="1", expected_output="1")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            t.id = "P2"  # type: ignore[misc]

    def test_dict_roundtrip(self):
        t = TestCase(id="P1", input="5", expected_output="6")
        d = t.to_dict()
        self.assertEqual(d, {"id": "P1", "input": "5", "expected_output": "6"})
        self.assertEqual(TestCase.from_dict(d), t)
        self.assertEqual(TestCase.from_dict(dict(d)), t)

    def test_from_dict_missing_key(self):
        with self.assertRaises(ValueError):
            TestCase.from_dict({"id": "P1", "input": "1"})
        with self.assertRaises(TypeError):
            TestCase.from_dict("nope")  # type: ignore[arg-type]


class ProblemValidationTests(unittest.TestCase):
    def test_valid_minimal(self):
        p = Problem(**make_valid_kwargs())
        self.assertEqual(p.problem_id, "TEST-001")
        self.assertEqual(p.concept_id, "C1")
        self.assertEqual(p.language, "python")
        self.assertEqual(p.difficulty, 2)
        self.assertEqual(p.variant_role, "canonical")
        self.assertEqual(p.misconception_ids, ("C1-M01",))
        self.assertEqual(len(p.public_tests), 1)
        self.assertEqual(len(p.hidden_tests), 1)

    def test_invalid_concept(self):
        for bad in ["C0", "C9", "CX", "", "  "]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                Problem(**make_valid_kwargs(concept_id=bad))
        with self.assertRaises(TypeError):
            Problem(**make_valid_kwargs(concept_id=None))
        with self.assertRaises(TypeError):
            Problem(**make_valid_kwargs(concept_id=123))

    def test_invalid_language(self):
        for bad in ["c++", "ruby", "", "  ", "py"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                Problem(**make_valid_kwargs(language=bad))
        with self.assertRaises(TypeError):
            Problem(**make_valid_kwargs(language=None))

    def test_difficulty_bounds(self):
        for bad in [0, 6, -1, 100]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                Problem(**make_valid_kwargs(difficulty=bad))

    def test_difficulty_types_rejected(self):
        for bad in [True, False, 2.0, "2", None]:
            with self.assertRaises(TypeError, msg=repr(bad)):
                Problem(**make_valid_kwargs(difficulty=bad))

    def test_invalid_variant_role(self):
        for bad in ["canon", "isomorphic", "", "  "]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                Problem(**make_valid_kwargs(variant_role=bad))
        with self.assertRaises(TypeError):
            Problem(**make_valid_kwargs(variant_role=None))

    def test_unknown_misconception(self):
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(misconception_ids=["C1-M99"]))
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(misconception_ids=["X-SYNTAX"]))

    def test_misconception_must_belong_to_concept(self):
        # C2-M01 belongs to C2, not C1.
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(concept_id="C1", misconception_ids=["C2-M01"]))
        # Sanity: same ID is fine under its own concept.
        p = Problem(**make_valid_kwargs(concept_id="C2", misconception_ids=["C2-M01"]))
        self.assertEqual(p.misconception_ids, ("C2-M01",))

    def test_misconception_empty_or_duplicate(self):
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(misconception_ids=[]))
        with self.assertRaises(ValueError):
            Problem(
                **make_valid_kwargs(misconception_ids=["C1-M01", "C1-M01"])
            )
        with self.assertRaises(TypeError):
            Problem(**make_valid_kwargs(misconception_ids="C1-M01"))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Problem(**make_valid_kwargs(misconception_ids=[123]))  # type: ignore[list-item]

    def test_public_tests_required(self):
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(public_tests=[]))

    def test_hidden_may_be_empty(self):
        p = Problem(**make_valid_kwargs(hidden_tests=[]))
        self.assertEqual(tuple(p.hidden_tests), ())
        self.assertEqual(len(p.all_tests()), 1)

    def test_duplicate_test_ids_rejected(self):
        dup_public = [
            TestCase(id="P1", input="1", expected_output="1"),
            TestCase(id="P1", input="2", expected_output="2"),
        ]
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(public_tests=dup_public))
        cross = dict(
            make_valid_kwargs(
                public_tests=[TestCase(id="T1", input="1", expected_output="1")],
                hidden_tests=[TestCase(id="T1", input="2", expected_output="2")],
            )
        )
        with self.assertRaises(ValueError):
            Problem(**cross)

    def test_tests_must_be_testcase(self):
        with self.assertRaises(TypeError):
            Problem(
                **make_valid_kwargs(public_tests=[{"id": "P1"}])  # type: ignore[list-item]
            )

    def test_text_fields_required(self):
        for f in ["title", "description", "starter_code", "input_format", "output_format"]:
            with self.assertRaises((TypeError, ValueError), msg=f):
                Problem(**make_valid_kwargs(**{f: ""}))
            with self.assertRaises((TypeError, ValueError), msg=f):
                Problem(**make_valid_kwargs(**{f: "   "}))
            with self.assertRaises(TypeError, msg=f):
                Problem(**make_valid_kwargs(**{f: None}))

    def test_constraints_required(self):
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(constraints=[]))
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(constraints=[""]))
        with self.assertRaises(TypeError):
            Problem(**make_valid_kwargs(constraints="1 <= n"))  # type: ignore[arg-type]

    def test_id_patterns(self):
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(problem_id="has space"))
        with self.assertRaises(ValueError):
            Problem(**make_valid_kwargs(isomorphic_group_id=""))

    def test_frozen(self):
        p = Problem(**make_valid_kwargs())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            p.title = "x"  # type: ignore[misc]


class NormalizationTests(unittest.TestCase):
    def test_concept_language_role_misconception_normalized(self):
        p = Problem(
            **make_valid_kwargs(
                concept_id=" c1 ",
                language=" Python ",
                variant_role=" Canonical ",
                misconception_ids=[" c1-m01 "],
            )
        )
        self.assertEqual(p.concept_id, "C1")
        self.assertEqual(p.language, "python")
        self.assertEqual(p.variant_role, "canonical")
        self.assertEqual(p.misconception_ids, ("C1-M01",))

    def test_is_valid_helpers(self):
        self.assertTrue(is_valid_variant_role("canonical"))
        self.assertTrue(is_valid_variant_role(" TRANSFER "))
        self.assertTrue(is_valid_variant_role("Remedial"))
        self.assertFalse(is_valid_variant_role("canon"))
        self.assertFalse(is_valid_variant_role(""))
        self.assertFalse(is_valid_variant_role(None))
        self.assertTrue(is_valid_difficulty(1))
        self.assertTrue(is_valid_difficulty(5))
        self.assertFalse(is_valid_difficulty(0))
        self.assertFalse(is_valid_difficulty(6))
        self.assertFalse(is_valid_difficulty(True))
        self.assertFalse(is_valid_difficulty("3"))
        self.assertEqual(tuple(VALID_VARIANT_ROLES), ("canonical", "transfer", "remedial"))


class SerializationTests(unittest.TestCase):
    def test_problem_dict_roundtrip(self):
        p = Problem(**make_valid_kwargs())
        d = p.to_dict()
        self.assertIsInstance(d["constraints"], list)
        self.assertIsInstance(d["public_tests"], list)
        self.assertEqual(Problem.from_dict(d), p)
        # Deterministic: twice equal.
        self.assertEqual(Problem.from_dict(d).to_dict(), d)

    def test_from_dict_accepts_testcase_objects(self):
        p = Problem(**make_valid_kwargs())
        d = p.to_dict()
        d["public_tests"] = list(p.public_tests)
        d["hidden_tests"] = list(p.hidden_tests)
        self.assertEqual(Problem.from_dict(d), p)

    def test_from_dict_missing_keys(self):
        d = Problem(**make_valid_kwargs()).to_dict()
        del d["title"]
        with self.assertRaises(ValueError):
            Problem.from_dict(d)
        with self.assertRaises(TypeError):
            Problem.from_dict([])  # type: ignore[arg-type]

    def test_lists_accepted_as_tuples(self):
        p = Problem(
            **make_valid_kwargs(
                constraints=["a", "b"],
                public_tests=[TestCase(id="P1", input="1", expected_output="1")],
                hidden_tests=[TestCase(id="H1", input="2", expected_output="2")],
                misconception_ids=["C1-M01"],
            )
        )
        self.assertIsInstance(p.constraints, tuple)
        self.assertIsInstance(p.public_tests, tuple)
        self.assertIsInstance(p.misconception_ids, tuple)


class ExamplesTests(unittest.TestCase):
    def test_three_examples(self):
        self.assertEqual(len(EXAMPLE_PROBLEMS), 3)
        self.assertIn(EXAMPLE_PYTHON_PROBLEM, EXAMPLE_PROBLEMS)
        self.assertIn(EXAMPLE_JAVA_PROBLEM, EXAMPLE_PROBLEMS)
        self.assertIn(EXAMPLE_TRANSFER_PROBLEM, EXAMPLE_PROBLEMS)
        self.assertEqual(len(EXAMPLE_BY_ID), 3)

    def test_example_languages(self):
        self.assertEqual(EXAMPLE_PYTHON_PROBLEM.language, "python")
        self.assertEqual(EXAMPLE_JAVA_PROBLEM.language, "java")
        self.assertEqual(EXAMPLE_TRANSFER_PROBLEM.language, "python")

    def test_example_roles(self):
        self.assertEqual(EXAMPLE_PYTHON_PROBLEM.variant_role, "canonical")
        self.assertEqual(EXAMPLE_JAVA_PROBLEM.variant_role, "canonical")
        self.assertEqual(EXAMPLE_TRANSFER_PROBLEM.variant_role, "transfer")

    def test_transfer_shares_isomorphic_group(self):
        self.assertEqual(
            EXAMPLE_TRANSFER_PROBLEM.isomorphic_group_id,
            EXAMPLE_PYTHON_PROBLEM.isomorphic_group_id,
        )
        self.assertNotEqual(
            EXAMPLE_TRANSFER_PROBLEM.problem_id, EXAMPLE_PYTHON_PROBLEM.problem_id
        )
        self.assertEqual(
            EXAMPLE_TRANSFER_PROBLEM.concept_id, EXAMPLE_PYTHON_PROBLEM.concept_id
        )

    def test_examples_have_tests_and_misconceptions(self):
        for p in EXAMPLE_PROBLEMS:
            self.assertGreaterEqual(len(p.public_tests), 1, p.problem_id)
            self.assertGreaterEqual(len(p.hidden_tests), 1, p.problem_id)
            self.assertGreaterEqual(len(p.misconception_ids), 1, p.problem_id)
            self.assertTrue(p.title.strip(), p.problem_id)
            self.assertTrue(p.description.strip(), p.problem_id)
            self.assertTrue(p.starter_code.strip(), p.problem_id)
            self.assertEqual(len(p.test_ids()), len(set(p.test_ids())))
            # Round-trip through dicts preserves equality.
            self.assertEqual(Problem.from_dict(p.to_dict()), p)

    def test_all_tests_order_public_first(self):
        p = EXAMPLE_PYTHON_PROBLEM
        all_ids = p.test_ids()
        n_public = len(p.public_tests)
        self.assertEqual(
            all_ids[:n_public], tuple(t.id for t in p.public_tests)
        )


if __name__ == "__main__":
    unittest.main()
