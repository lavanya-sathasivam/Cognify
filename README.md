# COGNIFY

**COGNIFY** is an AI-powered adaptive programming learning system that understands **WHY** a student struggles with programming concepts, provides targeted interventions based on the student's diagnosed weaknesses and learning history, and verifies whether the student actually improved.

> Current state: implementation through Step 17 is complete, including the
> Docker execution architecture fix (`ccfc49d fix execution service sandbox
> architecture`, working tree clean). Step 18 has NOT been started.
> The full learning loop works for the Python C3 slice
> (execution → Evidence Pack → diagnosis → learner model → intervention →
> retry → transfer → verification → adaptive recommendation) with a
> student-facing API and UI. See [Current limitations / prototype
> constraints](#19-current-limitations--prototype-constraints) and
> [Current implementation status](#20-current-implementation-status).

---

## 1. Project overview

Cognify is a closed-loop programming tutor. Instead of only telling a
student their code is wrong, it:

1. Executes the submission against tests in an isolated Docker sandbox.
2. Collects observed evidence (code, failing test, expected vs. actual output).
3. Diagnoses the likely misconception with evidence-grounded rules + LLM reasoning.
4. Updates a persistent learner model (mastery, trend, hint dependence, transfer).
5. Delivers a targeted intervention tied to that diagnosis.
6. Requires the student to retry, then solve a transfer problem in a new context.
7. Verifies genuine improvement before advancing the roadmap.

The current student-facing demo is primarily Python-focused, although Java
execution support exists in the execution service.

## 2. Problem Cognify solves

Beginners fail for different underlying reasons (off-by-one bounds,
range-exclusivity confusion, accumulator errors, etc.), but most tools only
report pass/fail or give generic hints. That leads to:

- Students fixing symptoms without fixing the misconception.
- No memory of past mistakes, so the same error recurs.
- No check that an intervention actually transferred to new problems.
- One-size-fits-all next steps instead of adaptive sequencing.

Cognify addresses this with a diagnosed → targeted → verified loop: every
failure produces evidence, every intervention cites that evidence, and every
claim of improvement must survive a transfer problem.

## 3. Core differentiator

- **Evidence-grounded diagnosis, not free-form guessing.** Deterministic rules
  for selected misconceptions must cite real evidence (`failed_test:<id>`,
  expected/actual output, code shape) and pass validation; the LLM cannot
  invent misconceptions or mutate learner state.
- **Deterministic learner/adaptive/verification ownership.** The AI service
  reasons semantically but never writes learner state. Mastery math lives in
  one place, adaptive ranking is rule-based (R1–R8), and verification uses a
  closed decision table.
- **Transfer-gated verification.** Passing the original problem is not enough:
  `VERIFIED_IMPROVED` requires passing a different-context transfer problem.
- **Fail-closed sandboxed execution.** Core backend never executes student
  code; all execution goes over HTTP to an isolated Docker sandbox.

## 4. Closed-loop adaptive learning flow

The core learning loop:

```
FAILURE
→ DIAGNOSIS
→ TARGETED INTERVENTION
→ RETRY
→ TRANSFER / RELATED PROBLEM
→ VERIFICATION
→ LEARNER MODEL UPDATE
→ ADAPTIVE NEXT ACTION
```

Expanded student loop:

```
Student chooses Python OR Java
→ Learning Roadmap
→ Concept Learning
→ Coding Problem
→ Code Execution + Test Evaluation
→ Root-Cause Diagnosis
→ Learner Profile Update
→ Targeted Hint / Intervention
→ Student Retry
→ Related / Isomorphic Problem
→ Learning Verification
→ Mastery Update
→ Adaptive Roadmap
```

The system distinguishes an isolated coding mistake, an implementation
mistake, a recurring misconception, a concept-level weakness, and verified
improvement after intervention.

## 5. System architecture

Services and packages:

```
apps/web
services/core-backend
services/ai-service
services/execution-service
packages/taxonomy
packages/mastery
packages/adaptive
packages/verification
packages/problem-schema
packages/problem-bank
problem-bank
infra
docs
```

Runtime request flow:

```
Student Browser
→ Core Backend
→ Execution Client (HTTP)
→ Execution Service
→ Docker Sandbox (isolated container)
→ execution result
→ Core Backend
→ diagnosis / learner model / adaptive / verification
→ response to Student
```

Architecture rules (enforced):

- Core backend must NOT directly execute student code.
- Core backend communicates with execution-service through HTTP
  (`POST /execute` via `execution_client.execute_problem`).
- Execution-service owns Docker-based code execution.
- AI service performs semantic diagnosis but does not write learner state
  and has no database access.
- Learner model (core-backend `learner_engine` + `packages/mastery`) owns
  mastery state; only core-backend mutates it.
- Adaptive engine makes deterministic next-action decisions (reads mastery,
  never computes it).
- Verification engine deterministically checks improvement (consumes
  outcomes, never executes code).
- Execution and AI services do not directly write the database.

One request flows through the existing components; the student API only
orchestrates them:

```
student code
  → execution-service (sandboxed run + test evaluation)
  → Evidence Pack (observed facts only)
  → diagnosis: deterministic C3 rules → LLM (if configured) → fallback
  → learner model: record attempt + mastery
  → intervention: structured object rendered by the UI (no invented advice)
  → retry → transfer problem
  → verification engine → closed loop writes + ranking
  → adaptive engine recommendation
```

Service ports (local defaults):

| Service | Port | Health |
|---------|------|--------|
| core-backend | 8000 | `GET http://localhost:8000/health` |
| ai-service | 8001 | `GET http://localhost:8001/health` |
| execution-service | 8002 | `GET http://localhost:8002/health` |
| web | 3000 | `http://localhost:3000` |

## 6. Repository structure

```text
Cognify/
├── apps/
│   └── web/                  # Next.js + TypeScript + Tailwind student UI
├── services/
│   ├── core-backend/         # FastAPI — product API + student slice + learner model + HTTP execution client
│   ├── ai-service/           # FastAPI — diagnosis rules / LLM / interventions
│   └── execution-service/    # FastAPI — stateless sandboxed code execution (Python + Java)
├── packages/
│   ├── taxonomy/             # Shared error taxonomy (concepts C1–C8, misconceptions, languages)
│   ├── mastery/              # Shared mastery formula + weakness rules (pure, deterministic)
│   ├── problem_schema/       # Shared problem JSON schemas
│   ├── evidence/             # EvidencePack builder (observed facts only)
│   ├── adaptive/             # Adaptive policy R1–R8 + ranking
│   ├── verification/         # Verification engine (closed decision table)
│   └── problem_bank/         # Problem loader + execution/diagnosis pipeline + journey
├── problem-bank/
│   ├── python/               # Python problems + tests (canonical + transfer + probe)
│   └── java/                 # Reserved (currently empty; Java UI flow not exposed)
├── tests/                    # Cross-service test suites (reserved)
├── docs/                     # Architecture / API notes (reserved, currently empty)
├── infra/                    # Deploy manifests (reserved, currently empty)
├── .venv/                    # Root Python virtual environment (local only, git-ignored)
├── .gitignore
├── .env.example              # Root env template (copy to .env)
├── Dockerfile                # Single shared image for all 3 Python services
├── requirements.txt          # Single shared Python deps for all services
├── docker-compose.yml        # Local orchestration for web + 3 services
└── README.md                 # Single project README (only one in repo)
```

## 7. Major modules and responsibilities

| Module | Owns | Must NOT do |
|--------|------|-------------|
| `services/core-backend` (`student.py`, `closed_loop.py`, `learner_engine.py`, `execution_client.py`) | Student API orchestration, learner-state writes, mastery transitions, closed-loop recording, HTTP call to execution-service | Execute student code directly; let the LLM mutate mastery |
| `services/ai-service` (`rules.py`, `service.py`, `llm_client.py`, `fallback.py`, `interventions.py`, `gate.py`, `validator.py`) | Evidence-grounded diagnosis, deterministic C3 rules, LLM diagnosis with strict validation, structured interventions | Write learner state, rank next actions, verify improvement, touch the DB |
| `services/execution-service` (`main.py`, `evaluator.py`, `python_runner.py`, `java_runner.py`, `sandbox.py`) | Stateless code execution + test evaluation for Python and Java | Diagnose, compute mastery, adapt, verify, access the DB |
| `packages/taxonomy` | Concepts C1–C8, misconceptions, cross-cutting errors, `SUPPORTED_LANGUAGES = (python, java)` | DB, AI, execution, adaptive logic |
| `packages/mastery` | Pure mastery formula + weakness rules | DB access (reads supplied values only) |
| `packages/evidence` | `EvidencePack` builder: observed execution + code + relevant history slice | Confirm misconceptions (candidates only; `confirmed_misconception_id` stays `None`) |
| `packages/adaptive` | Deterministic policy R1–R8 + ranking | Compute mastery, touch DB/LLM |
| `packages/verification` | Closed verification verdicts from already-produced outcomes | Execute code, compute mastery, rank, write DB |
| `packages/problem-schema` | Problem JSON validation | Execution/diagnosis |
| `packages/problem-bank` | Problem loading, execution/diagnosis pipeline, journey orchestration | Final product decisions (delegated to services) |
| `apps/web` | Student UI: problem view, submit, intervention display, retry/transfer, journey | Execute code in the browser; invent advice |

## 8. Diagnosis engine

Location: `services/ai-service/app/` + `packages/evidence/`.

- **Evidence first.** `EvidencePack` preserves raw execution output verbatim,
  lists misconceptions as *candidates* from the problem definition, and
  includes only the history slice relevant to `(concept, candidate IDs)`.
- **Deterministic rules first.** `rules.py` implements evidence-grounded rules
  for selected C3 Python misconceptions:
  - `C3_RANGE_BOUNDARY_EXCLUSION` → `C3-M01` (off-by-one bounds, e.g.
    `for i in range(len(nums) - 1)` missing the terminal element).
  - `C3_RANGE_EXCLUSIVITY` → `C3-M05` (e.g. `range(1, n)` for an inclusive
    1..n task).
  - Rules are pure functions of the pack (AST + integer comparisons), require
    corroborating static *and* dynamic evidence, fire at confidence `0.70`,
    and abstain (`None`) unless all predicates hold.
- **LLM second, fallback last.** On a rule miss, the configured LLM
  (`LLM_PROVIDER=openai` + key) may diagnose under strict validation; on any
  failure the safe fallback classifier is used. Empty provider (default) =
  deterministic rules + fallback mode.
- **Grounding.** Diagnosis cites code, failed tests, and expected/actual
  output. `evidence_refs` use only validator-accepted references
  (`failed_test:<id>` plus bare section names).
- **Interventions are structured, not generated.** `interventions.py` maps a
  validated diagnosis to a closed-vocabulary object (levels L1 NUDGE → L4
  RETEACH; types `BOUNDARY_CHECK`, `TRACE_LOOP`, `MICRO_LESSON`,
  `TARGETED_HINT`, `REMEDIAL_PROBLEM`). Escalation comes only from learner
  history (recurrence/occurrence counts), never from the current failure
  alone. Rule IDs and certainty details are controlled before display.
- The system does not allow the LLM to directly mutate mastery or adaptive
  state.

## 9. Learner model

Location: `services/core-backend/app/learner_engine.py` + `packages/mastery/`
+ `packages/evidence/models.py` snapshots.

- Tracks attempts, pass/fail history, mastery, mastery band
  (`novice`/`emerging`/`proficient`/`mastered`/`unknown`), trend
  (`unknown`/`stable`/`improving`/`declining`), hint dependence, transfer
  evidence (transfer attempts/successes/failures + success rate with an
  explicit canonical-vs-transfer breakdown and trailing per-attempt history),
  and recurring misconceptions (with supporting problem/group evidence).
- New `(journey, concept)` state starts at mastery `0.20` / band `novice` /
  trend `unknown` with zero counts.
- All state is namespaced per `(user, language_track)`; Python and Java
  journeys are separate rows and never mix.
- Mastery is updated only through the learner engine (consuming execution
  evidence + diagnoses); the pure formula lives in `packages/mastery`.
- History is append-only (`attempt`, `diagnosis`, `mastery_transition`,
  `recurring_detected`/`recurring_cleared` events explain "why is mastery X?").
  Each `mastery_transition` carries previous/current mastery, delta, reason,
  attempt number, hint/transfer flags, bands, trend, and evidence refs; read
  views clamp rates instead of crashing on inconsistent legacy counters, and
  adaptive evidence echoes pass/fail + transfer + recent-rate context while
  decisions stay deterministic (R1–R8 unchanged).
- Adaptive decisions are deterministic reads of this state.

## 10. Adaptive engine

Location: `packages/adaptive/` (policy R1–R8 + ranking).

Deterministic rules (transparent heuristic):

- R1 prerequisite gate: unmet prereq mastery → `REVIEW_PREREQUISITE`
  (priority 100, always first); suppresses `CHALLENGE`/`TRANSFER` downstream.
- R2 very low mastery (< 0.40) → `REVIEW_CONCEPT` + `REMEDIAL_PROBLEM`.
- R3 recurring misconception → review/remedial targeting it (+15 priority,
  reason says "Recurring weakness").
- R4 emerging [0.40, 0.60) → `PRACTICE_PROBLEM`.
- R5 proficient [0.60, 0.80) → `PRACTICE_PROBLEM` + `TRANSFER` when ready.
- R6 mastered (≥ 0.80) → `CHALLENGE_PROBLEM` (+ `TRANSFER` when ready),
  suppressed when recurring/declining/hint-high.
- R7 declining trend → +10 to review/practice.
- R8 high hint dependence (≥ 0.50) → +10 to review, suppress
  challenge/transfer.

Adaptive actions (closed set):

- `REVIEW_CONCEPT`
- `REMEDIAL_PROBLEM`
- `PRACTICE_PROBLEM`
- `CHALLENGE_PROBLEM`
- `TRANSFER_PROBLEM`
- `REVIEW_PREREQUISITE`

Priority = base + urgency (`round((1.0 − mastery) × 10)`) + boosts; ranking
lives in `ranking.py`. The UI never claims mastery unless the learner model
reports band `mastered`.

## 11. Verification engine

Location: `packages/verification/` (stdlib-only, deterministic).

Closed decision table on already-produced outcomes (never executes code,
never computes mastery, never ranks):

- Original retry missing → `INCOMPLETE` (not ready; never guess).
- Original retry non-`PASS` → `NOT_IMPROVED` (transfer ignored).
- Original `PASS` + transfer missing → `INCOMPLETE` (never claim verified).
- Original `PASS` + transfer non-`PASS` → `SURFACE_FIX`.
- Original `PASS` + transfer `PASS` → `VERIFIED_IMPROVED`.

Verification outcomes:

- `VERIFIED_IMPROVED`
- `SURFACE_FIX`
- `NOT_IMPROVED`
- `INCOMPLETE`

`PASS + PASS` means "verified improvement for this intervention / concept
instance" — explicitly NOT "the student mastered the concept". Mastery
remains owned by the learner engine, which consumes the result as evidence.

## 12. Problem bank

Location: `problem-bank/` (JSON + canonical solutions) loaded/validated via
`packages/problem-schema` and `packages/problem_bank/`.

Current Python problems (C3, `isomorphic_group_id` links variants):

| Problem ID | Title | Role | Group | Tests |
|------------|-------|------|-------|-------|
| `PY-C3-COUNT-DIV` | Count Divisible Numbers | canonical | `ISO-C3-COUNT-DIV` | 2 public + 3 hidden (5 total) |
| `PY-C3-COUNT-DIV-TRANSFER` | Count Cold Days | transfer | `ISO-C3-COUNT-DIV` | 2 public + 3 hidden (5 total) |
| `PY-C3-LOOP-MISCONCEPTION` | Sum One to N | remedial/probe | `ISO-C3-INCLUSIVE-SUM` | 2 public + 3 hidden (5 total) |

- Each problem declares `concept_id`, `language`, `difficulty`,
  `variant_role` (`canonical`/`transfer`/`remedial`), `misconception_ids`,
  starter code, I/O formats, and public + hidden tests.
- Transfer uses a different surface story but the related loop skill
  (counting with bounds + accumulator).
- The bank is intentionally small (C3 canonical + transfer + probe); it is
  not a large-scale catalog (see limitations).
- `problem-bank/java/` is reserved and currently empty.

## 13. Code execution architecture

Production path (Step 17, no direct execution in core-backend):

```
core-backend student.py
→ execution_client.execute_problem(problem, code) — HTTP POST EXECUTION_SERVICE_URL/execute
→ execution-service POST /execute (stateless: language + code + tests + timeout)
→ PythonRunner / JavaRunner
→ DockerSandboxRunner
→ isolated student container
→ ExecutionResult dict (validated shape) back to core-backend pipeline
```

- `execution_client` performs no execution itself, imports no Docker code,
  and never instantiates a sandbox runner.
- Single `POST /execute` carries ALL tests; the response is validated
  (`status`, `language`, counts, per-test entries, decisive-failure
  consistency) before downstream use.
- Failure mapping is fail-closed, never execute-locally:
  connection/timeout/5xx → `ExecutionServiceUnavailable` → HTTP 503;
  non-200/other or malformed shape → `ExecutionServiceBadResponse` → HTTP 502.
- Python runs `python /workspace/solution.py` per test
  (`python:3.11-slim`); Java compiles once (`javac /workspace/Main.java`,
  `eclipse-temurin:17-jdk`) and runs per test — currently the per-test run
  compiles and runs within the sandbox execution command
  (`javac /workspace/Main.java && java -cp /workspace Main`).
- Limits: student code capped at 100,000 chars (422 if exceeded);
  per-test timeout 5.0s; HTTP timeout scales with test count.

## 14. Docker sandbox/security

Location: `services/execution-service/app/sandbox.py`.

- Student code NEVER runs on the host. The only subprocesses target the
  Docker CLI (no `shell=True` / `eval` / `exec` / `compile` / `os.system`).
- Docker-managed temporary named volume (e.g. `cognify-exec-vol-<id>`): a
  helper container (`python:3.11-slim`, network `none`, same resource
  limits) receives source text as JSON over stdin and ONLY writes files —
  it never executes student code.
- Student code runs inside a separate restricted container mounting that
  volume at `/workspace` (`-w /workspace -i`), with:
  `--network none`, `--memory 256m` (+ `--memory-swap 256m`),
  `--cpus 1.0`, `--pids-limit 128`. No host environment variables are
  forwarded.
- Filenames are validated (reject absolute paths and `..` traversal) before
  Docker is invoked; the temporary volume is removed best-effort afterwards.
- Sandbox fails closed if Docker is unavailable
  (`SandboxUnavailableError` → HTTP 503); student code is never executed
  directly on the host as a fallback.
- No stronger isolation (gVisor/Firecracker or similar) is implemented —
  do not claim it.

Product/security constraints (current):

- Server-side execution only; the frontend never executes code.
- Student code size limits enforced server-side.
- Hidden test expected outputs are never serialized to the client
  (`to_student_view` redaction; transfer never reveals isomorphic grouping).
- Server resolves all problem metadata from the bank; spoofed client
  metadata (concept/language/mastery/diagnosis/verification) is ignored.
- CORS allowlist exists (`STUDENT_CORS_ORIGINS`, default
  `http://localhost:3000`).

## 15. Student-facing flow

Verified browser journey (Python C3):

1. Student receives the Count Divisible Numbers problem (`PY-C3-COUNT-DIV`).
2. Student submits an incorrect solution.
3. Execution service runs the submission in Docker.
4. Tests fail and evidence is collected.
5. Cognify identifies the relevant loop misconception.
6. Targeted intervention is shown.
7. Student retries with corrected code.
8. Original problem passes all 5 tests.
9. Cognify unlocks a transfer problem (`PY-C3-COUNT-DIV-TRANSFER`,
   "Count Cold Days").
10. Transfer problem uses a different context but related loop skill.
11. Student solves the transfer problem.
12. Transfer passes.
13. Verification returns `VERIFIED_IMPROVED`.
14. Learner model is updated.
15. Adaptive engine recommends the next action based on mastery.

Pass/fail recording: failures are recorded immediately with their diagnosis;
passes flow through the closed loop once transfer evidence exists
(append-only log; re-submitting a transfer re-records attempts, no dedup).

## 16. API overview

Student API (core-backend, all JSON; the shorthand `POST /sessions` etc.
maps to these `/student/*` routes):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/student/sessions` | Start a session; returns the canonical problem (`PY-C3-COUNT-DIV`) |
| GET | `/student/problems/{id}` | Safe problem metadata (never any expected outputs) |
| POST | `/student/submissions` | Submit code for canonical (incl. retry) or transfer; runs execution → evidence → diagnosis → learner update → intervention / verification |
| GET | `/student/journey` | Stage, verification, recommendations |

Also: `GET /health` per service; execution-service adds `GET /languages`
and `POST /execute`.

## 17. Language tracks

The student chooses **ONE** programming language for their learning journey:

- **Python**
- **Java**

All learning state (roadmap, mastery, history) is namespaced per
`(user, language_track)`. The taxonomy supports both tracks
(`SUPPORTED_LANGUAGES = (python, java)`), and the execution service runs
both in Docker — but the current student-facing demo is Python-focused and
the UI does not expose the Java track yet. `problem-bank/java/` is reserved.

Concept taxonomy:

| Code | Concept |
|------|---------|
| C1 | Variables, Types, Operators, I/O |
| C2 | Conditionals & Boolean Logic |
| C3 | Loops & Iteration Control |
| C4 | Functions / Methods, Parameters, Scope & Return |
| C5 | Lists / Arrays & Strings |
| C6 | Dictionaries / Maps, Sets & Nested Structures |
| C7 | OOP: Classes, Objects, Encapsulation, Inheritance |
| C8 | Recursion, Exceptions & Algorithmic Complexity Basics |

Deterministic diagnosis rules currently cover selected C3/Python patterns
only; everything else uses the LLM (if configured) or the safe fallback.

## 18. Testing and validation

Last verified results (implementation through Step 17):

- Core backend: **149 passed**
- Execution service: **39 passed**
- Packages: **255 passed, 27 subtests passed**
- Frontend: **7 Vitest tests passed**
- TypeScript: `npx tsc --noEmit` **passed**
- ESLint: `npm run lint` **passed**
- Next.js production build: `npm run build` **passed**
- Docker/browser end-to-end (wrong → diagnosis → retry → transfer →
  `VERIFIED_IMPROVED`): **verified successfully**

Run suites from the repo root (venv activated):

```powershell
# Backend suites
python -m unittest discover -s services/core-backend/tests -t .
python -m unittest discover -s services/ai-service/tests -t .
python -m unittest discover -s services/execution-service/tests -t .
python -m unittest discover -s packages/problem_bank/tests -t .
python -m unittest discover -s packages/evidence/tests -t .
python -m unittest discover -s packages/taxonomy/tests -t .
python -m unittest discover -s packages/mastery/tests -t .
python -m unittest discover -s packages/adaptive/tests -t .
python -m unittest discover -s packages/verification/tests -t .
python -m unittest discover -s packages/problem_schema/tests -t .
```

From `apps\web`:

```powershell
npm test          # vitest: UI states (render/submit/fail/retry/transfer/verified/errors)
npx tsc --noEmit  # type checking
npm run lint      # eslint
npm run build     # production build
```

## 19. Current limitations / prototype constraints

Honest boundaries for reviewers:

- Student persistence is **process-local/in-memory** (each student session
  owns one in-memory SQLite database via a shared-connection pool; sessions
  live in a process-local store). Restarting the backend loses sessions.
  This is NOT production-grade persistent multi-user storage.
- Deterministic diagnosis rules cover **selected C3/Python patterns**
  only; everything else uses the LLM (if configured) or the safe fallback.
- The **Java track is not exposed** in the UI (bank placeholder only),
  even though Java execution works in the execution service.
- The **problem bank is small** (C3 canonical + transfer + probe).
- The UI never claims mastery unless the learner model reports band
  `mastered`.
- Re-submitting a transfer re-records attempts (append-only learner log,
  no dedup).
- Execution requires a working Docker daemon; without it,
  execution-dependent endpoints fail closed (503) instead of running
  student code anywhere unsafe.
- Production would need durable persistence, auth, and stronger
  sandbox/deployment infrastructure — none of that is in this prototype.

This prototype intentionally does **not** include:

- Authentication / payments
- Teacher or analytics dashboards
- Gamification or chat interfaces
- Java UI or AI problem generation
- New LLM providers, RAG, or vector databases
- Production cloud infrastructure

## 20. Current implementation status

Completed milestones (Steps 1–17):

1. Project architecture and repository structure
2. Concept taxonomy (C1–C8)
3. Problem schema
4. Evidence pack
5. Grounded AI diagnosis
6. Learner model + mastery engine
7. Adaptive engine (R1–R8 + ranking)
8. Verification engine (closed decision table)
9. Closed-loop learning orchestration
10. Problem bank + execution pipeline
11. Problem bank expansion (transfer/remedial problems)
12. End-to-end adaptive learning journey
13. Evidence-grounded diagnosis and intervention rules
14. Student-facing vertical slice
15. Product hardening and demo readiness
16. Docker-based execution architecture
17. Core-backend → execution-service HTTP execution client and Docker
    sandbox fix (`ccfc49d`)

### IMPLEMENTED / VERIFIED

- Closed-loop learning flow (failure → diagnosis → intervention → retry →
  transfer → verification → model update → adaptive action) for the Python
  C3 slice, verified end-to-end in Docker + browser.
- HTTP execution path: core-backend → execution-service → Docker sandbox
  (Python and Java run in Docker; network disabled; resource limits; named
  volumes; fail-closed).
- Evidence-grounded deterministic C3 rules + validated LLM path + fallback;
  structured interventions with closed vocabularies.
- Learner model (attempts, mastery, band, trend, hint dependence, transfer
  evidence, recurring misconceptions) with append-only history.
- Deterministic adaptive recommendations (6 action types) and verification
  verdicts (4 outcomes).
- Student API (`/student/sessions`, `/student/problems/{id}`,
  `/student/submissions`, `/student/journey`) with CORS allowlist, code
  size limits, hidden-output redaction, and spoofed-metadata rejection.
- Student-facing Next.js UI with Vitest coverage, clean `tsc`, `lint`, and
  production `build`.

### PARTIALLY IMPLEMENTED

- Language tracks: Python end-to-end via UI; Java executes in the sandbox
  but has no bank content and no student UI flow.
- Problem bank: 3 Python C3 problems only (canonical, transfer, probe) —
  enough for the demo loop, not a curriculum.
- Persistence: process-local/in-memory session store (+ SQLite dev
  defaults); no durable multi-user database.
- LLM diagnosis: works when configured (`openai` + key), otherwise rules +
  fallback; no evaluation harness.

### FUTURE WORK (not started; do not treat as present)

- Instructor/admin dashboard.
- Advanced analytics dashboard.
- Production database persistence (durable multi-user storage).
- Authentication (and payments).
- Large-scale problem bank (beyond the 3-problem C3 slice).
- Full Java student UI flow.
- Production deployment / cloud infrastructure.
- LLM evaluation benchmarks.
- Stronger isolation such as gVisor/Firecracker.
- Step 18 and beyond.

## 21. Local development / Docker run instructions

### 1. Clone + Python venv (Windows PowerShell)

```powershell
git clone <repo-url> Cognify
cd Cognify
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

> Note: single shared `requirements.txt` at repo root covers all 3 Python services
> (`core-backend`, `ai-service`, `execution-service`). Do not create per-service copies.

### 2. Env files

```powershell
copy .env.example .env
copy services\core-backend\.env.example services\core-backend\.env
copy services\ai-service\.env.example services\ai-service\.env
copy services\execution-service\.env.example services\execution-service\.env
```

### 3. Run backends locally (3 terminals, venv activated)

```powershell
uvicorn app.main:app --reload --port 8000  # from services/core-backend
uvicorn app.main:app --reload --port 8001  # from services/ai-service
uvicorn app.main:app --reload --port 8002  # from services/execution-service
```

Verify:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8002/health
```

### 4. Run frontend

```powershell
cd apps\web
npm install
npm run dev
# open http://localhost:3000
```

The web app calls core-backend at `NEXT_PUBLIC_CORE_BACKEND_URL`
(defaults to `http://localhost:8000`; set it in the environment before
`npm run dev` / `npm run build` to point elsewhere).

### 5. Run everything with Docker (alternative)

```powershell
copy .env.example .env
docker compose up --build
```

Then open `http://localhost:3000` and the three `/health` endpoints above.
`core-backend` is wired to `http://execution-service:8002`, and
`execution-service` mounts `/var/run/docker.sock` so it can launch sandbox
containers (sibling containers, not host execution).

> Note: live code execution shells out to the `docker` CLI, so the host
> running a backend (local or in compose) needs a working Docker daemon.
> Without it, execution-dependent endpoints fail closed (503) instead of
> running student code anywhere unsafe.

### Environment variables

Only these are read by the current application (everything else in the
`.env.example` files is reserved for later steps):

| Variable | Used by | Required? | Effect |
|----------|---------|-----------|--------|
| `STUDENT_CORS_ORIGINS` | core-backend | No (defaults to `http://localhost:3000`) | Browser origins allowed to call the API |
| `NEXT_PUBLIC_CORE_BACKEND_URL` | web | No (defaults to `http://localhost:8000`) | Backend URL baked into the frontend at dev/build time |
| `LLM_PROVIDER` (`""`/`openai`/`mock`) | ai-service | No (empty = deterministic rules + fallback mode) | Enables LLM diagnosis when set with a key |
| `LLM_API_KEY` | ai-service | Only with `LLM_PROVIDER=openai` | Secret; never leaves the backend |
| `LLM_MODEL` / `LLM_BASE_URL` / `LLM_TIMEOUT_SECONDS` | ai-service | No (safe defaults) | Model routing / endpoint / timeout |
| `DATABASE_URL` | core-backend | No (defaults to local SQLite) | Dev persistence default; the student slice still uses a process-local session store — leave unset for the demo |
| `PORT`, `*_PORT`, `*_URL` | compose/services | Only under Docker | Wiring between containers (`EXECUTION_SERVICE_URL=http://execution-service:8002`) |

LLM modes: **configured** (`LLM_PROVIDER=openai` + key → model diagnosis with
strict validation and fallback on any failure) vs **deterministic**
(default empty provider → evidence-grounded rules, then the safe fallback
classifier). Student sessions work identically in both; no secrets are
ever exposed to the frontend.

---

## Demo Journey

Concise verified path (Python C3, 5 tests per problem):

```
Wrong submission (PY-C3-COUNT-DIV, e.g. range(len(nums) - 1) misses last element)
→ diagnosis (loop-bounds misconception, grounded in failing tests + expected/actual)
→ targeted intervention ("Check whether your loop processes the final required element.")
→ retry (fixed loop visits every element)
→ original problem pass (5/5)
→ transfer problem unlocked (PY-C3-COUNT-DIV-TRANSFER, "Count Cold Days")
→ transfer pass (5/5, same skill, new context)
→ VERIFIED_IMPROVED (original + transfer both PASS)
→ adaptive next recommendation (deterministic next action from mastery)
```

Full click-through (3–5 minutes). Prerequisites: backend on `:8000`,
frontend on `:3000`, Docker daemon available for live execution.

| Step | Do | What you see | Responsible component |
|------|----|--------------|----------------------|
| 1 | Open `http://localhost:3000` | Cognify header, Python track | web UI |
| 2 | Read the problem | “Count Divisible Numbers” (C3) | problem bank via student API |
| 3 | Paste the buggy loop (`for i in range(len(nums) - 1): …`) and Submit | — | execution-service (sandboxed) |
| 4 | Read the result | FAILED, why it failed, failing-test evidence, “Check whether your loop processes the final required element.” | Evidence Pack → diagnosis (evidence-grounded rule) → intervention |
| 5 | Fix the loop to visit every element, Submit again | — | same pipeline, retry path |
| 6 | Read the result | “Good improvement”, Continue button | student API (transfer unlocked) |
| 7 | Continue | “Count Cold Days” (shown as a related challenge, not as an isomorphic variant) | problem bank |
| 8 | Submit a correct transfer solution | — | execution-service |
| 9 | Read the result | VERIFIED_IMPROVED (“You solved the original problem and applied the idea…”) | verification engine + closed loop |
| 10 | Read the next step | Recommended action + reason (+ problem title when available) | adaptive engine |

Buggy starter for step 3 (fails decisive `P2` and hidden boundary tests):

```python
def count_divisible(nums, k):
    count = 0
    for i in range(len(nums) - 1):
        if nums[i] % k == 0:
            count += 1
    return count
```
