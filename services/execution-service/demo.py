"""Step 5 demo: example execution flows (SIMULATED sandbox, no Docker needed).

Simulates exactly what the Docker sandbox would return for a canned
submission, then runs the real pipeline:

  student code -> language runner -> problem_schema.TestCase list
  -> evaluator -> ExecutionResult

Run from repo root:  python services/execution-service/demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]  # .../Cognify
for _p in (str(_ROOT), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.evaluator import evaluate  # noqa: E402
from app.java_runner import JavaRunner  # noqa: E402
from app.python_runner import PythonRunner  # noqa: E402
from app.sandbox import FakeSandboxRunner, SandboxResult  # noqa: E402
from packages.problem_schema import TestCase  # noqa: E402

PYTHON_CODE = "a, b = map(int, input().split())\nprint(a + b)\n"
JAVA_CODE = (
    "import java.util.*;\n"
    "public class Main {\n"
    "  public static void main(String[] args) {\n"
    "    Scanner s = new Scanner(System.in);\n"
    "    int a = s.nextInt(); int b = s.nextInt();\n"
    "    System.out.println(a + b);\n"
    "  }\n"
    "}\n"
)
CASES = [
    TestCase(id="t1", input="2 3", expected_output="5"),
    TestCase(id="t2", input="10 20", expected_output="30"),
]


def _show(title: str, result) -> None:
    print(f"--- {title} ---")
    print(json.dumps(result.to_dict(), indent=2))
    print()


def main() -> None:
    # -- Python flow: both tests pass -------------------------------------
    py_sandbox = FakeSandboxRunner(
        default=SandboxResult(stdout="", stderr="", exit_code=0, timed_out=False, time_ms=38)
    )
    py_sandbox.program(
        ["python", "/workspace/solution.py"], "2 3",
        SandboxResult(stdout="5\n", stderr="", exit_code=0, timed_out=False, time_ms=38),
    ).program(
        ["python", "/workspace/solution.py"], "10 20",
        SandboxResult(stdout="30\n", stderr="", exit_code=0, timed_out=False, time_ms=41),
    )
    _show(
        "Python flow (sum of two ints, 2 tests)",
        evaluate("python", PYTHON_CODE, CASES, PythonRunner(sandbox=py_sandbox)),
    )

    # -- Java flow: compile ok, second test fails --------------------------
    java_sandbox = FakeSandboxRunner(
        default=SandboxResult(stdout="", stderr="", exit_code=0, timed_out=False, time_ms=10)
    )
    java_sandbox.program(
        ["javac", "/workspace/Main.java"], "",
        SandboxResult(stdout="", stderr="", exit_code=0, timed_out=False, time_ms=820),
    ).program(
        ["java", "-cp", "/workspace", "Main"], "2 3",
        SandboxResult(stdout="5\n", stderr="", exit_code=0, timed_out=False, time_ms=95),
    ).program(
        ["java", "-cp", "/workspace", "Main"], "10 20",
        SandboxResult(stdout="25\n", stderr="", exit_code=0, timed_out=False, time_ms=97),
    )
    _show(
        "Java flow (compile ok, t2 wrong output)",
        evaluate("java", JAVA_CODE, CASES, JavaRunner(sandbox=java_sandbox)),
    )


if __name__ == "__main__":
    main()
