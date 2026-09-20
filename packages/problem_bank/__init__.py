"""COGNIFY problem_bank package — Step 12 (deterministic, stdlib-only core).

Contents:
- ``loader``: deterministic JSON -> ``packages.problem_schema.Problem``
  loading for ``problem-bank/python/*.json`` (no LLM, no DB, no randomness).
- ``pipeline``: thin integration reusing the existing Step 5
  (execution-service evaluator + sandbox runners), Step 6
  (EvidencePack builder), Step 7 (diagnosis service with fallback), and
  Step 10/11 (verification + closed-loop planning). It duplicates no
  policy, formula, or sandbox logic.

Security: this package never executes student code itself. Execution
happens only through the existing execution-service sandbox abstraction
(Docker in production, scripted fakes in tests). No subprocess, no shell,
no network, no filesystem writes, no environment reads here.
"""

from .loader import (
    DEFAULT_BANK_DIR,
    list_problem_ids,
    load_all_problems,
    load_problem,
    load_problem_file,
)

__all__ = [
    "DEFAULT_BANK_DIR",
    "list_problem_ids",
    "load_all_problems",
    "load_problem",
    "load_problem_file",
]
