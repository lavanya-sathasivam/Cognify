"""COGNIFY problem_bank package — Steps 12 + 21A (deterministic, stdlib-only core).

Contents:
- ``loader``: deterministic JSON -> ``packages.problem_schema.Problem``
  loading for ``problem-bank/python/*.json`` (default, backward
  compatible) plus explicit ``*_all`` helpers discovering both
  ``problem-bank/python`` and ``problem-bank/java`` (Step 21A).
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
    DEFAULT_BANK_ROOT,
    SUPPORTED_BANK_LANGUAGES,
    list_problem_ids,
    list_problem_ids_all,
    load_all_problems,
    load_all_problems_all,
    load_problem,
    load_problem_all,
    load_problem_file,
)

__all__ = [
    "DEFAULT_BANK_DIR",
    "DEFAULT_BANK_ROOT",
    "SUPPORTED_BANK_LANGUAGES",
    "list_problem_ids",
    "list_problem_ids_all",
    "load_all_problems",
    "load_all_problems_all",
    "load_problem",
    "load_problem_all",
    "load_problem_file",
]
