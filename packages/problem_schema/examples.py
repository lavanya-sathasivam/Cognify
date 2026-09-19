"""COGNIFY problem_schema — 3 example problems (data only, never executed)."""
from __future__ import annotations

from .models import Problem, TestCase


EXAMPLE_PYTHON_PROBLEM = Problem(
    problem_id="PY-C3-001",
    concept_id="C3",
    language="python",
    difficulty=2,
    title="Sum of Even Numbers",
    description=(
        "Read an integer n and compute the sum of all even numbers "
        "from 1 to n inclusive. If no even number exists in the range, "
        "the result is 0."
    ),
    constraints=(
        "1 <= n <= 10000",
        "Input is a single integer.",
    ),
    starter_code=(
        "def sum_evens(n: int) -> int:\n"
        '    """Return the sum of even numbers from 1 to n inclusive."""\n'
        "    # TODO: implement using a loop and an accumulator\n"
        "    raise NotImplementedError\n"
    ),
    input_format="A single integer n.",
    output_format="A single integer: the sum of evens in [1, n].",
    public_tests=(
        TestCase(id="P1", input="5", expected_output="6"),
        TestCase(id="P2", input="1", expected_output="0"),
    ),
    hidden_tests=(
        TestCase(id="H1", input="10", expected_output="30"),
        TestCase(id="H2", input="100", expected_output="2550"),
    ),
    isomorphic_group_id="ISO-C3-SUM-EVENS",
    variant_role="canonical",
    misconception_ids=("C3-M01", "C3-M04"),
)

EXAMPLE_JAVA_PROBLEM = Problem(
    problem_id="JAVA-C2-001",
    concept_id="C2",
    language="java",
    difficulty=2,
    title="Sign Classifier",
    description=(
        "Read an integer x and print its sign: "
        '"POSITIVE" if x > 0, "NEGATIVE" if x < 0, "ZERO" if x == 0.'
    ),
    constraints=(
        "-1000000000 <= x <= 1000000000",
        "Input is a single integer.",
    ),
    starter_code=(
        "public class SignClassifier {\n"
        "    public static String classify(int x) {\n"
        "        // TODO: return \"POSITIVE\", \"NEGATIVE\", or \"ZERO\"\n"
        "        return null;\n"
        "    }\n"
        "}\n"
    ),
    input_format="A single integer x.",
    output_format='A single line: "POSITIVE", "NEGATIVE", or "ZERO".',
    public_tests=(
        TestCase(id="P1", input="5", expected_output="POSITIVE"),
        TestCase(id="P2", input="-3", expected_output="NEGATIVE"),
    ),
    hidden_tests=(
        TestCase(id="H1", input="0", expected_output="ZERO"),
        TestCase(id="H2", input="1000000000", expected_output="POSITIVE"),
    ),
    isomorphic_group_id="ISO-C2-SIGN-CLASSIFY",
    variant_role="canonical",
    misconception_ids=("C2-M01", "C2-M03"),
)

EXAMPLE_TRANSFER_PROBLEM = Problem(
    problem_id="PY-C3-002",
    concept_id="C3",
    language="python",
    difficulty=2,
    title="Sum of Odd Numbers",
    description=(
        "Read an integer n and compute the sum of all odd numbers "
        "from 1 to n inclusive. This is the transfer variant of "
        "'Sum of Even Numbers': same loop-bounds and accumulator skill, "
        "different parity filter."
    ),
    constraints=(
        "1 <= n <= 10000",
        "Input is a single integer.",
    ),
    starter_code=(
        "def sum_odds(n: int) -> int:\n"
        '    """Return the sum of odd numbers from 1 to n inclusive."""\n'
        "    # TODO: implement using a loop and an accumulator\n"
        "    raise NotImplementedError\n"
    ),
    input_format="A single integer n.",
    output_format="A single integer: the sum of odds in [1, n].",
    public_tests=(
        TestCase(id="P1", input="5", expected_output="9"),
        TestCase(id="P2", input="1", expected_output="1"),
    ),
    hidden_tests=(
        TestCase(id="H1", input="10", expected_output="25"),
        TestCase(id="H2", input="2", expected_output="1"),
    ),
    isomorphic_group_id="ISO-C3-SUM-EVENS",
    variant_role="transfer",
    misconception_ids=("C3-M01", "C3-M04"),
)

EXAMPLE_PROBLEMS: tuple[Problem, ...] = (
    EXAMPLE_PYTHON_PROBLEM,
    EXAMPLE_JAVA_PROBLEM,
    EXAMPLE_TRANSFER_PROBLEM,
)

EXAMPLE_BY_ID: dict[str, Problem] = {p.problem_id: p for p in EXAMPLE_PROBLEMS}

__all__ = [
    "EXAMPLE_BY_ID",
    "EXAMPLE_JAVA_PROBLEM",
    "EXAMPLE_PROBLEMS",
    "EXAMPLE_PYTHON_PROBLEM",
    "EXAMPLE_TRANSFER_PROBLEM",
]
