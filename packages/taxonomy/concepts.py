"""COGNIFY taxonomy — concepts.

Deterministic, framework-independent (stdlib only).
No DB, AI, execution, or adaptive logic here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    """A single learning concept in the Cognify curriculum."""

    id: str  # e.g. "C1"
    title: str  # short label, e.g. "Variables, Types, Operators, I/O"
    description: str  # one-paragraph scope definition
    topics: tuple[str, ...]  # canonical sub-topics covered
    prerequisites: tuple[str, ...]  # concept IDs that should come first


CONCEPTS: tuple[Concept, ...] = (
    Concept(
        id="C1",
        title="Variables, Types, Operators, I/O",
        description=(
            "Declaring and using variables, primitive/reference types, "
            "arithmetic/relational/logical operators, precedence, "
            "type conversion, and basic console input/output."
        ),
        topics=(
            "variables-and-assignment",
            "primitive-types",
            "operators-and-precedence",
            "type-conversion",
            "console-io",
        ),
        prerequisites=(),
    ),
    Concept(
        id="C2",
        title="Conditionals & Boolean Logic",
        description=(
            "Branching with if/elif/else (Python) and if/else-if/else plus "
            "switch (Java), boolean operators, short-circuit evaluation, "
            "De Morgan laws, and nested conditions."
        ),
        topics=(
            "if-else-branching",
            "boolean-operators",
            "short-circuit-evaluation",
            "nested-conditionals",
            "switch-and-chained-comparison",
        ),
        prerequisites=("C1",),
    ),
    Concept(
        id="C3",
        title="Loops & Iteration Control",
        description=(
            "Definite and indefinite iteration, loop bounds and termination, "
            "break/continue, nested loops, and iteration over collections."
        ),
        topics=(
            "for-loops",
            "while-loops",
            "loop-bounds-and-termination",
            "break-continue",
            "nested-loops",
        ),
        prerequisites=("C1", "C2"),
    ),
    Concept(
        id="C4",
        title="Functions / Methods, Parameters, Scope & Return",
        description=(
            "Defining and calling functions/methods, parameters vs arguments, "
            "return values, local vs global/enclosing scope, and call semantics."
        ),
        topics=(
            "function-definition-and-calls",
            "parameters-and-arguments",
            "return-values",
            "scope-and-shadowing",
            "call-semantics",
        ),
        prerequisites=("C1", "C2", "C3"),
    ),
    Concept(
        id="C5",
        title="Lists / Arrays & Strings",
        description=(
            "Indexed sequences (Python lists, Java arrays/ArrayList), string "
            "handling, indexing, slicing/substrings, aliasing vs copying, "
            "and immutability of strings."
        ),
        topics=(
            "indexing",
            "slicing-and-substrings",
            "aliasing-vs-copying",
            "string-immutability",
            "length-vs-last-index",
        ),
        prerequisites=("C1", "C3", "C4"),
    ),
    Concept(
        id="C6",
        title="Dictionaries / Maps, Sets & Nested Structures",
        description=(
            "Key-based collections (dict/HashMap), sets, membership tests, "
            "missing-key handling, and safe access to nested structures."
        ),
        topics=(
            "dict-map-basics",
            "sets-and-membership",
            "missing-key-handling",
            "mutation-during-iteration",
            "nested-structure-access",
        ),
        prerequisites=("C1", "C3", "C5"),
    ),
    Concept(
        id="C7",
        title="OOP: Classes, Objects, Encapsulation, Inheritance",
        description=(
            "Classes vs instances, constructors, fields vs methods, "
            "encapsulation and access control, inheritance with super calls, "
            "and static vs instance members."
        ),
        topics=(
            "class-vs-instance",
            "constructors",
            "encapsulation-and-access-control",
            "inheritance-and-super",
            "static-vs-instance",
        ),
        prerequisites=("C1", "C4", "C5"),
    ),
    Concept(
        id="C8",
        title="Recursion, Exceptions & Algorithmic Complexity Basics",
        description=(
            "Recursive decomposition with base/progress cases, raising and "
            "handling exceptions without swallowing them, and Big-O reasoning "
            "for simple loops and recursion."
        ),
        topics=(
            "base-and-progress-cases",
            "raising-and-handling-exceptions",
            "recursion-vs-iteration",
            "big-o-basics",
        ),
        prerequisites=("C2", "C3", "C4", "C7"),
    ),
)

_CONCEPT_BY_ID: dict[str, Concept] = {c.id: c for c in CONCEPTS}

CONCEPT_IDS: tuple[str, ...] = tuple(c.id for c in CONCEPTS)
