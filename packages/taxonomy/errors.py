"""COGNIFY taxonomy — misconceptions and cross-cutting errors.

Naming:
  Concept misconception IDs: "<CONCEPT>-M<NN>", e.g. "C1-M01".
  Cross-cutting IDs: "X-<NAME>", e.g. "X-SYNTAX".

Language scope:
  languages=("python", "java")          -> shared / language-agnostic
  languages=("python",)                 -> Python-specific
  languages=("java",)                   -> Java-specific
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Language = Literal["python", "java"]

PYTHON: str = "python"
JAVA: str = "java"
SUPPORTED_LANGUAGES: tuple[str, ...] = (PYTHON, JAVA)


@dataclass(frozen=True)
class Misconception:
    """One diagnosable misconception/error pattern within a concept."""

    id: str  # e.g. "C1-M01"
    concept_id: str  # e.g. "C1"
    name: str  # short label
    description: str  # what the student gets wrong and why it matters
    languages: tuple[str, ...]  # subset of SUPPORTED_LANGUAGES
    typical_signal: str  # observable symptom (output/behavior/code shape)


@dataclass(frozen=True)
class CrossCuttingError:
    """Outcome-level error orthogonal to any single concept."""

    id: str  # e.g. "X-SYNTAX"
    name: str
    description: str
    typical_signal: str


# ---------------------------------------------------------------------------
# C1 — Variables, Types, Operators, I/O
# ---------------------------------------------------------------------------
_C1: tuple[Misconception, ...] = (
    Misconception(
        id="C1-M01",
        concept_id="C1",
        name="assignment-vs-equality",
        description="Uses `=` where `==` is meant (or vice versa); confuses storing a value with testing equality.",
        languages=(PYTHON, JAVA),
        typical_signal="Condition always true / variable overwritten inside `if`; e.g. `if x = 5`.",
    ),
    Misconception(
        id="C1-M02",
        concept_id="C1",
        name="type-coercion-and-division",
        description="Misunderstands implicit conversion and division semantics (integer vs float division, string+int).",
        languages=(PYTHON, JAVA),
        typical_signal="`7/2 == 3` surprise, or `TypeError: can only concatenate str`, or Java `7/2 == 3` truncation.",
    ),
    Misconception(
        id="C1-M03",
        concept_id="C1",
        name="unconverted-input",
        description="Forgets console input arrives as text and must be converted before arithmetic/comparison.",
        languages=(PYTHON, JAVA),
        typical_signal="`input()`/`Scanner.nextLine()` result used directly in arithmetic; lexicographic compare.",
    ),
    Misconception(
        id="C1-M04",
        concept_id="C1",
        name="operator-precedence",
        description="Misorders evaluation of `not`/`and`/`or` and arithmetic/relational operators; omits needed parentheses.",
        languages=(PYTHON, JAVA),
        typical_signal="`not a == b` read as `not (a == b)` vs `(not a) == b`; `a + b * c` errors.",
    ),
    Misconception(
        id="C1-M05",
        concept_id="C1",
        name="python-dynamic-typing-and-none",
        description="Python-specific: assumes a variable keeps one type; mishandles `None` and dynamic rebinding.",
        languages=(PYTHON,),
        typical_signal="`NoneType has no attribute ...`; variable rebound from `int` to `str` then misused.",
    ),
    Misconception(
        id="C1-M06",
        concept_id="C1",
        name="java-static-types-scanner-and-init",
        description="Java-specific: wrong static type declaration, use of uninitialized locals, or `Scanner` method mismatch.",
        languages=(JAVA,),
        typical_signal="`variable might not have been initialized`; `nextInt()` followed by skipped `nextLine()`; lossy-conversion error.",
    ),
)

# ---------------------------------------------------------------------------
# C2 — Conditionals & Boolean Logic
# ---------------------------------------------------------------------------
_C2: tuple[Misconception, ...] = (
    Misconception(
        id="C2-M01",
        concept_id="C2",
        name="boolean-operator-confusion",
        description="Confuses `and`/`or`/`not` semantics; writes `x == 1 or 2` style conditions that are always truthy.",
        languages=(PYTHON, JAVA),
        typical_signal="`if x == 1 or 2:` always true; `&&`/`||` swapped.",
    ),
    Misconception(
        id="C2-M02",
        concept_id="C2",
        name="demorgan-negation",
        description="Mis-negates compound conditions; fails to distribute `not` over `and`/`or`.",
        languages=(PYTHON, JAVA),
        typical_signal="`not (a and b)` rewritten as `not a and not b` instead of `not a or not b`.",
    ),
    Misconception(
        id="C2-M03",
        concept_id="C2",
        name="branch-coverage-and-nesting",
        description="Misses `else`/`elif` branches or mis-nests conditions so some paths are unreachable or unhandled.",
        languages=(PYTHON, JAVA),
        typical_signal="Edge inputs fall through with no output; deeply nested `if` with dead branches.",
    ),
    Misconception(
        id="C2-M04",
        concept_id="C2",
        name="truthiness-vs-explicit-compare",
        description="Relies on truthiness (`if x:`) where an explicit comparison is required, or vice versa.",
        languages=(PYTHON, JAVA),
        typical_signal="`if count:` treats `0` as false unintentionally; empty string/list treated as false.",
    ),
    Misconception(
        id="C2-M05",
        concept_id="C2",
        name="python-chained-comparison",
        description="Python-specific: misreads chained comparisons (`1 < x < 5`) or tries C-style `1 < x && x < 5` incorrectly.",
        languages=(PYTHON,),
        typical_signal="`1 < x < 5` assumed to be `(1 < x) < 5`; chained form avoided or mis-parenthesized.",
    ),
    Misconception(
        id="C2-M06",
        concept_id="C2",
        name="java-switch-fallthrough-and-string-compare",
        description="Java-specific: omits `break` causing fallthrough, or compares strings with `==` instead of `.equals()`.",
        languages=(JAVA,),
        typical_signal="Multiple `case` bodies execute; `if (s == \"yes\")` never true for equal content.",
    ),
)

# ---------------------------------------------------------------------------
# C3 — Loops & Iteration Control
# ---------------------------------------------------------------------------
_C3: tuple[Misconception, ...] = (
    Misconception(
        id="C3-M01",
        concept_id="C3",
        name="off-by-one-bounds",
        description="Loop runs one iteration too many or too few due to `<` vs `<=` or 0- vs 1-based bounds.",
        languages=(PYTHON, JAVA),
        typical_signal="Last element skipped or `IndexError`/`ArrayIndexOutOfBoundsException` on final iteration.",
    ),
    Misconception(
        id="C3-M02",
        concept_id="C3",
        name="non-termination",
        description="Loop condition never becomes false; update step missing or in the wrong direction.",
        languages=(PYTHON, JAVA),
        typical_signal="Program hangs on `while` with unchanged flag/counter; execution timeout.",
    ),
    Misconception(
        id="C3-M03",
        concept_id="C3",
        name="break-continue-semantics",
        description="Confuses `break` (exit loop) with `continue` (skip to next iteration), or misplaces them in nesting.",
        languages=(PYTHON, JAVA),
        typical_signal="`continue` where `break` needed keeps looping; inner `break` assumed to exit outer loop.",
    ),
    Misconception(
        id="C3-M04",
        concept_id="C3",
        name="accumulator-and-loop-var-reuse",
        description="Fails to initialize/reset an accumulator, or reuses the loop variable after the loop as if meaningful.",
        languages=(PYTHON, JAVA),
        typical_signal="Running total carries over between calls; stale loop variable used after loop ends.",
    ),
    Misconception(
        id="C3-M05",
        concept_id="C3",
        name="python-range-exclusivity",
        description="Python-specific: forgets `range(stop)` excludes `stop`; misuses `range` step or `for-else`.",
        languages=(PYTHON,),
        typical_signal="`range(1, n)` expected to include `n`; `range(len(xs))` vs direct iteration confusion.",
    ),
    Misconception(
        id="C3-M06",
        concept_id="C3",
        name="java-for-header-and-iterator",
        description="Java-specific: miswrites classic `for (init; cond; update)` header or mutates a list while iterating it.",
        languages=(JAVA,),
        typical_signal="`for (int i = 0; i <= n; i++)` overruns; `ConcurrentModificationException` on remove-in-loop.",
    ),
)

# ---------------------------------------------------------------------------
# C4 — Functions / Methods, Parameters, Scope & Return
# ---------------------------------------------------------------------------
_C4: tuple[Misconception, ...] = (
    Misconception(
        id="C4-M01",
        concept_id="C4",
        name="value-vs-reference-call-semantics",
        description="Wrong mental model of argument passing: expects rebinding a parameter to mutate the caller, or vice versa.",
        languages=(PYTHON, JAVA),
        typical_signal="Reassigning a parameter and expecting caller to see it; surprised that mutating a list is visible.",
    ),
    Misconception(
        id="C4-M02",
        concept_id="C4",
        name="scope-and-shadowing",
        description="Confuses local, enclosing/global scope; accidentally shadows a variable or reads before assignment.",
        languages=(PYTHON, JAVA),
        typical_signal="`UnboundLocalError` / unexpected global unchanged after assignment inside function.",
    ),
    Misconception(
        id="C4-M03",
        concept_id="C4",
        name="missing-or-ignored-return",
        description="Omits `return`, returns in only some branches, or ignores the returned value at the call site.",
        languages=(PYTHON, JAVA),
        typical_signal="Function yields `None`/`void` misuse; computed value printed inside instead of returned.",
    ),
    Misconception(
        id="C4-M04",
        concept_id="C4",
        name="arity-and-argument-order",
        description="Calls with wrong number/order of arguments; confuses positional vs keyword/overload resolution.",
        languages=(PYTHON, JAVA),
        typical_signal="`TypeError: takes N arguments`; swapped `(row, col)` producing transposed behavior.",
    ),
    Misconception(
        id="C4-M05",
        concept_id="C4",
        name="python-mutable-default-argument",
        description="Python-specific: uses a mutable default (`def f(xs=[])`) shared across calls.",
        languages=(PYTHON,),
        typical_signal="List argument accumulates values across independent calls.",
    ),
    Misconception(
        id="C4-M06",
        concept_id="C4",
        name="java-signatures-overloading-and-void",
        description="Java-specific: confuses overloads, omits return type, or tries to use a `void` result as a value.",
        languages=(JAVA,),
        typical_signal="`'void' type not allowed here`; wrong overload picked due to widening.",
    ),
)

# ---------------------------------------------------------------------------
# C5 — Lists / Arrays & Strings
# ---------------------------------------------------------------------------
_C5: tuple[Misconception, ...] = (
    Misconception(
        id="C5-M01",
        concept_id="C5",
        name="index-vs-length",
        description="Confuses valid index range `0..len-1` with length; accesses `xs[len(xs)]`.",
        languages=(PYTHON, JAVA),
        typical_signal="`IndexError` / `ArrayIndexOutOfBoundsException` on last-element access.",
    ),
    Misconception(
        id="C5-M02",
        concept_id="C5",
        name="aliasing-vs-copying",
        description="Assigns/copies a reference instead of the contents; two names unexpectedly share one list/array.",
        languages=(PYTHON, JAVA),
        typical_signal="Sorting `b = a` also reorders `a`; `copy()` vs `=` confusion.",
    ),
    Misconception(
        id="C5-M03",
        concept_id="C5",
        name="string-immutability",
        description="Treats strings as mutable; expects `s[i] = c` or in-place `upper()`/`replace()` to change the original.",
        languages=(PYTHON, JAVA),
        typical_signal="`'str' object does not support item assignment`; Java `s.toUpperCase();` result discarded.",
    ),
    Misconception(
        id="C5-M04",
        concept_id="C5",
        name="search-and-split-edge-cases",
        description="Mishandles not-found sentinels (`-1`/`None`), empty strings, or delimiters when splitting/joining.",
        languages=(PYTHON, JAVA),
        typical_signal="`.index()` ValueError unhandled; `split()` on missing delimiter returns whole string unexpectedly.",
    ),
    Misconception(
        id="C5-M05",
        concept_id="C5",
        name="python-slicing-and-negative-index",
        description="Python-specific: misuses slice bounds/step and negative indices (`xs[-1]`, `xs[a:b]`).",
        languages=(PYTHON,),
        typical_signal="`xs[0:len]` fine but `xs[-1]` assumed invalid; reversed slice `xs[5:0]` returns `[]`.",
    ),
    Misconception(
        id="C5-M06",
        concept_id="C5",
        name="java-array-vs-arraylist-and-string-equals",
        description="Java-specific: treats fixed-size arrays as resizable, or compares strings with `==`.",
        languages=(JAVA,),
        typical_signal="`ArrayIndexOutOfBoundsException` on `add`; `==` on strings fails despite equal text.",
    ),
)

# ---------------------------------------------------------------------------
# C6 — Dictionaries / Maps, Sets & Nested Structures
# ---------------------------------------------------------------------------
_C6: tuple[Misconception, ...] = (
    Misconception(
        id="C6-M01",
        concept_id="C6",
        name="missing-key-handling",
        description="Accesses a key that may not exist without a guard/default; confuses key lookup with index lookup.",
        languages=(PYTHON, JAVA),
        typical_signal="`KeyError` / `null` from `get()` dereferenced; counting pattern without init (`d[k] += 1`).",
    ),
    Misconception(
        id="C6-M02",
        concept_id="C6",
        name="mutation-during-iteration",
        description="Adds/removes dict/map/set entries while iterating over it.",
        languages=(PYTHON, JAVA),
        typical_signal="`RuntimeError: dictionary changed size during iteration` / `ConcurrentModificationException`.",
    ),
    Misconception(
        id="C6-M03",
        concept_id="C6",
        name="hashability-and-equality-contract",
        description="Uses unhashable/mutable keys or defines equality without a matching hash (Java `equals`/`hashCode`).",
        languages=(PYTHON, JAVA),
        typical_signal="`TypeError: unhashable type: 'list'`; Java map lookups fail despite `equals` being true.",
    ),
    Misconception(
        id="C6-M04",
        concept_id="C6",
        name="unsafe-nested-access",
        description="Chains nested lookups (`d[a][b][c]`) without checking intermediate levels exist.",
        languages=(PYTHON, JAVA),
        typical_signal="`KeyError` / `NullPointerException` deep inside nested access; no `.get()`/null guard.",
    ),
    Misconception(
        id="C6-M05",
        concept_id="C6",
        name="python-get-setdefault-and-set-semantics",
        description="Python-specific: misuses `dict.get`/`setdefault`/`Counter`, or assumes sets preserve duplicates/order.",
        languages=(PYTHON,),
        typical_signal="`d.get(k)` result used without default; duplicate counting via list instead of set/Counter.",
    ),
    Misconception(
        id="C6-M06",
        concept_id="C6",
        name="java-map-impl-ordering-and-optional-get",
        description="Java-specific: assumes `HashMap` iterates in insertion order, or mishandles absent keys/`Optional`.",
        languages=(JAVA,),
        typical_signal="Order-dependent test flakes on `HashMap`; should have used `LinkedHashMap`/`TreeMap`.",
    ),
)

# ---------------------------------------------------------------------------
# C7 — OOP
# ---------------------------------------------------------------------------
_C7: tuple[Misconception, ...] = (
    Misconception(
        id="C7-M01",
        concept_id="C7",
        name="class-vs-instance",
        description="Confuses class attributes/methods with instance state; accesses instance data from the class or vice versa.",
        languages=(PYTHON, JAVA),
        typical_signal="All objects share one mutated value (class attribute); `self`/`this` omitted or misused.",
    ),
    Misconception(
        id="C7-M02",
        concept_id="C7",
        name="constructor-misuse",
        description="Mis-implements initialization (`__init__`/constructor): wrong params, missing field assignment, or calling it directly.",
        languages=(PYTHON, JAVA),
        typical_signal="Fields left `None`/`null`; `__init__` returns a value; Java constructor has a return type declared.",
    ),
    Misconception(
        id="C7-M03",
        concept_id="C7",
        name="encapsulation-violation",
        description="Exposes/bypasses private state instead of using accessors; breaks invariants by direct field mutation.",
        languages=(PYTHON, JAVA),
        typical_signal="Public mutable fields mutated externally; underscore-private accessed directly in Python.",
    ),
    Misconception(
        id="C7-M04",
        concept_id="C7",
        name="inheritance-and-super",
        description="Misuses inheritance (is-a vs has-a), forgets `super().__init__`/`super(...)`, or breaks Liskov substitution.",
        languages=(PYTHON, JAVA),
        typical_signal="Subclass `__init__` never calls `super()`; overridden method changes signature/behavior.",
    ),
    Misconception(
        id="C7-M05",
        concept_id="C7",
        name="python-self-and-dunder",
        description="Python-specific: omits `self`, confuses instance/class/static methods, or misuses dunder methods.",
        languages=(PYTHON,),
        typical_signal="`takes 1 positional argument but 2 were given`; `@staticmethod` used where instance state needed.",
    ),
    Misconception(
        id="C7-M06",
        concept_id="C7",
        name="java-static-vs-instance-and-modifiers",
        description="Java-specific: calls instance members from `static`, misuses `static`, or picks wrong access modifier/abstract/interface.",
        languages=(JAVA,),
        typical_signal="`non-static method cannot be referenced from a static context`; `static` mutable state shared.",
    ),
)

# ---------------------------------------------------------------------------
# C8 — Recursion, Exceptions & Complexity
# ---------------------------------------------------------------------------
_C8: tuple[Misconception, ...] = (
    Misconception(
        id="C8-M01",
        concept_id="C8",
        name="missing-base-or-progress",
        description="Recursive function lacks a reachable base case or fails to shrink the problem toward it.",
        languages=(PYTHON, JAVA),
        typical_signal="`RecursionError` / `StackOverflowError`; base case present but never hit.",
    ),
    Misconception(
        id="C8-M02",
        concept_id="C8",
        name="exception-swallowing",
        description="Catches too broadly (`except:`/`catch (Exception e)`) and hides failures with empty handlers.",
        languages=(PYTHON, JAVA),
        typical_signal="Bare `except: pass` masks bugs; program silently produces wrong output instead of failing loudly.",
    ),
    Misconception(
        id="C8-M03",
        concept_id="C8",
        name="recursion-vs-iteration-and-depth",
        description="Chooses recursion where iteration fits (or vice versa) and ignores depth/stack limits.",
        languages=(PYTHON, JAVA),
        typical_signal="Deep linear recursion overflows; iterative rewrite would be trivial and safe.",
    ),
    Misconception(
        id="C8-M04",
        concept_id="C8",
        name="big-o-misjudgment",
        description="Underestimates cost of nested loops, repeated slicing/concatenation, or hidden work inside loops.",
        languages=(PYTHON, JAVA),
        typical_signal="`O(n)` claimed for nested loop; `s += s` in a loop assumed linear; TLE on large inputs.",
    ),
    Misconception(
        id="C8-M05",
        concept_id="C8",
        name="python-bare-except-and-recursion-limit",
        description="Python-specific: bare `except:` also catches `KeyboardInterrupt`/control-flow, recursion hits default limit (~1000).",
        languages=(PYTHON,),
        typical_signal="`except:` swallows `Ctrl-C`; `RecursionError: maximum recursion depth exceeded`.",
    ),
    Misconception(
        id="C8-M06",
        concept_id="C8",
        name="java-checked-exceptions-and-throws",
        description="Java-specific: mishandles checked exceptions (`throws` vs `try/catch`), or catches and rethrows poorly.",
        languages=(JAVA,),
        typical_signal="`unreported exception ... must be caught or declared`; empty `catch` with only `printStackTrace()`.",
    ),
)

MISCONCEPTIONS_BY_CONCEPT: dict[str, tuple[Misconception, ...]] = {
    "C1": _C1,
    "C2": _C2,
    "C3": _C3,
    "C4": _C4,
    "C5": _C5,
    "C6": _C6,
    "C7": _C7,
    "C8": _C8,
}

_MISCONCEPTION_BY_ID: dict[str, Misconception] = {
    m.id: m for group in MISCONCEPTIONS_BY_CONCEPT.values() for m in group
}

# ---------------------------------------------------------------------------
# Cross-cutting errors (orthogonal to concepts)
# ---------------------------------------------------------------------------
CROSS_CUTTING_ERRORS: tuple[CrossCuttingError, ...] = (
    CrossCuttingError(
        id="X-SYNTAX",
        name="syntax-error",
        description="Source violates grammar rules; parser rejects it before any execution.",
        typical_signal="`SyntaxError` (Python) at parse time; code does not run at all.",
    ),
    CrossCuttingError(
        id="X-COMPILE",
        name="compilation-error",
        description="Statically typed compilation fails (types, symbols, signatures); no bytecode/class file produced.",
        typical_signal="`javac` errors: cannot find symbol, incompatible types, missing `;`/`}`.",
    ),
    CrossCuttingError(
        id="X-RUNTIME",
        name="runtime-error",
        description="Program starts but raises an uncaught exception / crashes mid-execution.",
        typical_signal="Traceback / stack trace with exception type and line; non-zero exit.",
    ),
    CrossCuttingError(
        id="X-TIMEOUT",
        name="timeout",
        description="Execution exceeds the allowed time budget (infinite loop, blowup, deadlock, excessive sleep).",
        typical_signal="Runner kills process with TLE; no output within limit.",
    ),
    CrossCuttingError(
        id="X-WRONG-OUTPUT",
        name="wrong-output",
        description="Program terminates normally but output differs from expected (failed assertion/test).",
        typical_signal="Diff between actual vs expected stdout/return; assertion failure without crash.",
    ),
)

_CROSS_CUTTING_BY_ID: dict[str, CrossCuttingError] = {e.id: e for e in CROSS_CUTTING_ERRORS}

CROSS_CUTTING_IDS: tuple[str, ...] = tuple(e.id for e in CROSS_CUTTING_ERRORS)
