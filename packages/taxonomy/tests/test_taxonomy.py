"""Unit tests for packages/taxonomy (stdlib unittest, no third-party deps)."""
from __future__ import annotations

import unittest

from packages.taxonomy import (
    SUPPORTED_LANGUAGES,
    get_concept,
    get_concept_for_misconception,
    get_cross_cutting_error,
    get_misconception,
    is_valid_concept,
    is_valid_cross_cutting_error,
    is_valid_misconception,
    list_concept_ids,
    list_concepts,
    list_cross_cutting_errors,
    list_misconceptions,
    misconception_belongs_to,
)


class ConceptTests(unittest.TestCase):
    def test_eight_concepts_in_order(self):
        self.assertEqual(list_concept_ids(), ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"])
        concepts = list_concepts()
        self.assertEqual(len(concepts), 8)
        self.assertEqual([c.id for c in concepts], list_concept_ids())

    def test_concept_titles_match_spec(self):
        expected = {
            "C1": "Variables, Types, Operators, I/O",
            "C2": "Conditionals & Boolean Logic",
            "C3": "Loops & Iteration Control",
            "C4": "Functions / Methods, Parameters, Scope & Return",
            "C5": "Lists / Arrays & Strings",
            "C6": "Dictionaries / Maps, Sets & Nested Structures",
            "C7": "OOP: Classes, Objects, Encapsulation, Inheritance",
            "C8": "Recursion, Exceptions & Algorithmic Complexity Basics",
        }
        for cid, title in expected.items():
            self.assertEqual(get_concept(cid).title, title)

    def test_concept_metadata_complete(self):
        for c in list_concepts():
            self.assertTrue(c.description.strip())
            self.assertTrue(len(c.topics) >= 3, c.id)
            for pre in c.prerequisites:
                self.assertTrue(is_valid_concept(pre), f"{c.id} bad prereq {pre}")
            self.assertNotIn(c.id, c.prerequisites)

    def test_get_concept_normalizes(self):
        self.assertEqual(get_concept("c1").id, "C1")
        self.assertEqual(get_concept("  C2 ").id, "C2")

    def test_get_concept_unknown_raises(self):
        for bad in ["C0", "C9", "CX", "", "  ", "C10"]:
            with self.assertRaises(KeyError, msg=bad):
                get_concept(bad)

    def test_is_valid_concept(self):
        self.assertTrue(is_valid_concept("C1"))
        self.assertTrue(is_valid_concept("c8"))
        self.assertTrue(is_valid_concept(" C3 "))
        self.assertFalse(is_valid_concept("C9"))
        self.assertFalse(is_valid_concept(""))
        self.assertFalse(is_valid_concept(None))
        self.assertFalse(is_valid_concept(123))


class MisconceptionTests(unittest.TestCase):
    def test_every_concept_has_misconceptions(self):
        for cid in list_concept_ids():
            items = list_misconceptions(cid)
            self.assertGreaterEqual(len(items), 4, cid)
            for m in items:
                self.assertEqual(m.concept_id, cid)
                self.assertTrue(m.id.startswith(f"{cid}-M"))
                self.assertTrue(m.name.strip())
                self.assertTrue(m.description.strip())
                self.assertTrue(m.typical_signal.strip())
                self.assertTrue(m.languages)
                for lang in m.languages:
                    self.assertIn(lang, SUPPORTED_LANGUAGES)

    def test_misconception_ids_unique(self):
        seen: set[str] = set()
        for cid in list_concept_ids():
            for m in list_misconceptions(cid):
                self.assertNotIn(m.id, seen, f"duplicate {m.id}")
                seen.add(m.id)

    def test_each_concept_has_language_specific_entries(self):
        for cid in list_concept_ids():
            langs = {lang for m in list_misconceptions(cid) for lang in m.languages}
            self.assertIn("python", langs, cid)
            self.assertIn("java", langs, cid)
            py_only = [m for m in list_misconceptions(cid) if m.languages == ("python",)]
            java_only = [m for m in list_misconceptions(cid) if m.languages == ("java",)]
            self.assertTrue(py_only, f"{cid} needs a python-specific entry")
            self.assertTrue(java_only, f"{cid} needs a java-specific entry")

    def test_language_filter(self):
        all_c1 = list_misconceptions("C1")
        py = list_misconceptions("C1", language="python")
        java = list_misconceptions("C1", language="java")
        self.assertTrue(0 < len(py) < len(all_c1) + 1)
        self.assertTrue(0 < len(java) < len(all_c1) + 1)
        for m in py:
            self.assertIn("python", m.languages)
        for m in java:
            self.assertIn("java", m.languages)
        # shared entry appears in both filters
        shared = [m.id for m in all_c1 if set(m.languages) == {"python", "java"}]
        self.assertTrue(shared)
        self.assertIn(shared[0], [m.id for m in py])
        self.assertIn(shared[0], [m.id for m in java])
        # case/space tolerant
        self.assertEqual(
            [m.id for m in list_misconceptions("C1", language=" Python ")],
            [m.id for m in py],
        )
        with self.assertRaises(ValueError):
            list_misconceptions("C1", language="c++")
        with self.assertRaises(KeyError):
            list_misconceptions("C9")

    def test_get_and_validate_misconception(self):
        m = get_misconception("C2-M01")
        self.assertEqual(m.concept_id, "C2")
        self.assertEqual(get_misconception("c2-m01").id, "C2-M01")
        self.assertEqual(get_misconception("  C3-M02 ").id, "C3-M02")
        self.assertTrue(is_valid_misconception("C1-M01"))
        self.assertTrue(is_valid_misconception("c8-m06"))
        self.assertFalse(is_valid_misconception("C1-M99"))
        self.assertFalse(is_valid_misconception("X-SYNTAX"))  # cross-cutting is separate
        self.assertFalse(is_valid_misconception(""))
        self.assertFalse(is_valid_misconception(None))
        with self.assertRaises(KeyError):
            get_misconception("C1-M99")
        with self.assertRaises(KeyError):
            get_misconception("nope")

    def test_parent_and_belongs_to(self):
        self.assertEqual(get_concept_for_misconception("C4-M05").id, "C4")
        self.assertTrue(misconception_belongs_to("C4-M05", "C4"))
        self.assertTrue(misconception_belongs_to("c4-m05", "c4"))
        self.assertFalse(misconception_belongs_to("C4-M05", "C5"))
        self.assertFalse(misconception_belongs_to("C4-M99", "C4"))
        self.assertFalse(misconception_belongs_to(None, "C4"))


class CrossCuttingTests(unittest.TestCase):
    def test_five_required_errors(self):
        ids = [e.id for e in list_cross_cutting_errors()]
        self.assertEqual(
            ids,
            ["X-SYNTAX", "X-COMPILE", "X-RUNTIME", "X-TIMEOUT", "X-WRONG-OUTPUT"],
        )
        names = {e.name for e in list_cross_cutting_errors()}
        self.assertEqual(
            names,
            {"syntax-error", "compilation-error", "runtime-error", "timeout", "wrong-output"},
        )
        for e in list_cross_cutting_errors():
            self.assertTrue(e.description.strip())
            self.assertTrue(e.typical_signal.strip())

    def test_get_and_validate_cross_cutting(self):
        self.assertEqual(get_cross_cutting_error("x-timeout").id, "X-TIMEOUT")
        self.assertEqual(get_cross_cutting_error(" X-SYNTAX ").name, "syntax-error")
        self.assertTrue(is_valid_cross_cutting_error("X-RUNTIME"))
        self.assertTrue(is_valid_cross_cutting_error("x-compile"))
        self.assertFalse(is_valid_cross_cutting_error("C1-M01"))
        self.assertFalse(is_valid_cross_cutting_error(""))
        self.assertFalse(is_valid_cross_cutting_error(None))
        with self.assertRaises(KeyError):
            get_cross_cutting_error("X-NOPE")

    def test_deterministic_repeat_calls(self):
        self.assertEqual(list_concept_ids(), list_concept_ids())
        self.assertEqual(
            [m.id for m in list_misconceptions("C5")],
            [m.id for m in list_misconceptions("C5")],
        )
        self.assertEqual(
            [e.id for e in list_cross_cutting_errors()],
            [e.id for e in list_cross_cutting_errors()],
        )


if __name__ == "__main__":
    unittest.main()
