# Cognify Internal Working & Viva Handbook

> **Audience:** Cognify team members preparing for a company / final-review style discussion (viva).
> **Goal:** Read this document and be able to explain confidently what every major part of Cognify does,
> why it exists, and how data flows through the system.
> **Rule used while writing:** every claim was checked against the actual repository code.
> Status labels are used everywhere: `[IMPLEMENTED]`, `[PARTIALLY IMPLEMENTED]`, `[PLANNED / NOT IMPLEMENTED]`.
> Anything inferred from code (not stated in comments/docs) is marked `Inferred from implementation.`
>
> - **Repository state at time of writing:** implementation through **Step 20B complete** (per `README.md`);
>   read-only student data APIs (`GET /student/concepts`, `GET /student/history`,
>   `GET /student/problems`) light up Learn/Progress/History/Home with real learner state.
> - **Date of writing:** 2026-09-20. No application code was modified to produce this document.
> - **Service ports (local):** core-backend `8000` · ai-service `8001` · execution-service `8002` · web `3000`.

## Status legend (used in every section)

| Label | Meaning |
|---|---|
| `[IMPLEMENTED]` | Present in code and wired into the running flow (with file evidence). |
| `[PARTIALLY IMPLEMENTED]` | Present but incomplete, prototype-scoped, or not wired end-to-end. |
| `[PLANNED / NOT IMPLEMENTED]` | Referenced in docs/env/comments but with no working implementation. |

## How to study this document

1. **Beginner path:** read Sections A → E → T → U → AA → AB. That gives you the story end-to-end.
2. **Technical path:** read Sections F → S in order (APIs, execution, evidence, diagnosis, learner model, mastery, adaptive, verification).
3. **Viva-cram path:** read Sections W → X → Y → Z, then rehearse AA (5-minute talk) and AB (30-second answer).
4. Boxes marked **“Remember this”** are the one-liners reviewers expect you to say out loud.

## Table of contents

- [A — Cognify in one page](#a--cognify-in-one-page)
- [B — Complete system architecture](#b--complete-system-architecture)
- [C — Complete repository map](#c--complete-repository-map)
- [D — File-by-file responsibility map](#d--file-by-file-responsibility-map)
- [E — End-to-end student journey](#e--end-to-end-student-journey)
- [F — API map](#f--api-map)
- [G — Execution pipeline](#g--execution-pipeline)
- [H — Evidence pack](#h--evidence-pack)
- [I — AI diagnosis](#i--ai-diagnosis)
- [J — Misconception taxonomy](#j--misconception-taxonomy)
- [K — Learner model](#k--learner-model)
- [L — Mastery calculation](#l--mastery-calculation)
- [M — Recurring misconception detection](#m--recurring-misconception-detection)
- [N — Adaptive engine](#n--adaptive-engine)
- [O — Verification engine](#o--verification-engine)
- [P — Closed loop](#p--closed-loop)
- [Q — Problem bank](#q--problem-bank)
- [R — Frontend](#r--frontend)
- [S — Security](#s--security)
- [T — Data flow chart](#t--data-flow-chart)
- [U — “Who does what?” table](#u--who-does-what-table)
- [V — Why did we design it this way?](#v--why-did-we-design-it-this-way)
- [W — Company-style questions](#w--company-style-questions)
- [X — Endpoint questions](#x--endpoint-questions)
- [Y — File-level viva questions](#y--file-level-viva-questions)
- [Z — “If they ask me to draw on the board”](#z--if-they-ask-me-to-draw-on-the-board)
- [AA — 5-minute explanation](#aa--5-minute-explanation)
- [AB — 30-second explanation](#ab--30-second-explanation)
- [AC — Current implementation status](#ac--current-implementation-status)
- [AD — Future steps](#ad--future-steps)

---

## A — Cognify in one page

### SIMPLE EXPLANATION

Cognify is a **closed-loop programming tutor**. A normal coding platform tells a student
“your code is wrong”. Cognify asks **why** it is wrong, remembers the reason, teaches
that specific reason, and then **proves the student really improved** before moving on.

### TECHNICAL EXPLANATION

Cognify is a multi-service system (Next.js frontend + FastAPI core-backend + FastAPI
ai-service + FastAPI execution-service + pure-Python `packages/` libraries + a JSON
problem bank) that implements an evidence-grounded learning loop: execute → collect
evidence → diagnose a taxonomy misconception → record it in a persistent learner model →
deliver a targeted intervention → require retry + transfer → verify improvement →
recommend the next action deterministically.

### 1. What problem are we solving?

Beginners fail for **different underlying reasons** (off-by-one bounds, range-exclusivity
confusion, accumulator errors, …), but most tools only report pass/fail or give generic
hints. That causes (per `README.md` §2):

- students fixing **symptoms** without fixing the misconception;
- **no memory** of past mistakes, so the same error recurs;
- **no check** that an intervention actually transferred to new problems;
- **one-size-fits-all** next steps instead of adaptive sequencing.

### 2. What is Cognify?

Cognify is a closed-loop programming tutor that understands **WHY** a student struggles,
provides **targeted interventions** based on diagnosed weaknesses + learning history, and
**verifies** whether the student actually improved (`README.md` §1). `[IMPLEMENTED]` for
the Python C3 slice; other concepts are `[PARTIALLY IMPLEMENTED]` (bank exists, rules/UX
are C3-scoped — see §AC).

### 3. Who is the user?

The **student** learning introductory programming (currently Python; Java execution
exists in the service but has no student-facing track — §AC). There is no teacher,
admin, or auth concept in the code: the frontend keeps one throwaway learning session
per browser (`apps/web/src/components/session.tsx`: “This is NOT authentication and NOT
a user account”).

### 4. What happens when a student submits code? (short version)

1. Frontend sends **only** `{session_id, problem_id, code}` to `POST /student/submissions`.
2. Core-backend resolves the problem **server-side** (client cannot choose tests/concept).
3. Code is executed by the **execution-service inside a Docker sandbox** (never on the host).
4. On failure, an **EvidencePack** (code + failing test + expected vs actual + history) is built.
5. The failure is **diagnosed** to one taxonomy misconception (deterministic C3 rules first,
   then LLM, then safe fallback — §I).
6. The attempt is **recorded in the learner model** (mastery moves by a fixed formula — §L).
7. The student gets an **evidence-citing intervention** (e.g. `BOUNDARY_CHECK` for `C3-M01`).
8. The student **retries**; after passing, a **transfer problem** (same skill, new story) unlocks.
9. **Verification** compares original-retry vs transfer (`VERIFIED_IMPROVED` needs PASS+PASS).
10. The **adaptive engine** deterministically recommends the next action (review / remedial /
    practice / transfer / challenge / prerequisite).

### 5. What makes Cognify different from a normal coding platform?

| Normal coding platform | Cognify |
|---|---|
| Reports pass/fail per test. | Reports pass/fail **plus the root-cause misconception** with cited evidence. |
| Stateless attempts. | Every attempt updates a **persistent learner model** (mastery, trend, misconception counters, recurring flags, history). |
| “Next problem” is a static list. | Next action is **computed deterministically** from mastery + recurrency + trend + hint dependence + prerequisites (R1–R8, §N). |
| Passing once = done. | Passing once is **not enough**: a transfer problem must also pass (`VERIFIED_IMPROVED`, §O). |

### 6. What makes Cognify different from simply asking ChatGPT for an explanation?

- ChatGPT guesses from code text. Cognify diagnoses from **observed execution evidence**
  (decisive failed test, expected vs actual, code shape via AST) and **rejects hallucinations**:
  the misconception ID must be a pack candidate, the concept must match, confidence must be
  ≥ 0.50, and evidence refs must cite the failure — otherwise a deterministic fallback fires (§I).
- ChatGPT has no memory or guarantees. Cognify has a **deterministic learner state** the LLM
  is **forbidden to write** (`services/core-backend/app/db.py`: “AI service MUST NOT import
  this”), a fixed **mastery formula** (§L), and a rule-based **adaptive policy** (§N).
- ChatGPT cannot verify learning. Cognify requires a **transfer pass** and records both
  attempts before claiming improvement (§O–§P).

### 7. What is the core closed-loop idea?

> **Failure is data. Diagnosis names the cause. Intervention targets the cause. Transfer proves
> the fix. The learner model remembers everything, and the next step is computed — not guessed.**

### Main flow chart (memorize this order)

```text
Student
 ↓  (writes code for the assigned problem)
Problem
 ↓  (server resolves canonical problem + hidden tests; client never sees them)
Code Submission
 ↓  (POST /student/submissions with session_id, problem_id, code only)
Code Execution
 ↓  (execution-service runs code against public+hidden tests in Docker sandbox)
Failure Evidence
 ↓  (EvidencePack: code, decisive failed test, expected vs actual, stderr, history)
Diagnosis
 ↓  (deterministic C3 rules → LLM → fallback; exactly one misconception ID + confidence)
Intervention
 ↓  (level L1–L4 from history + type from misconception, e.g. BOUNDARY_CHECK)
Retry
 ↓  (student fixes code and resubmits the SAME problem)
Transfer Problem
 ↓  (same isomorphic group/skill, new surface story; unlocks only after canonical pass)
Verification
 ↓  (PASS+PASS = VERIFIED_IMPROVED; PASS+FAIL = SURFACE_FIX; retry-fail = NOT_IMPROVED)
Learner Model Update
 ↓  (record_attempt: mastery recomputed, counters incremented, recurring re-evaluated)
Adaptive Next Action
 ↓  (R1–R8 policy + ranking; e.g. REVIEW_CONCEPT, REMEDIAL_PROBLEM, TRANSFER_PROBLEM…)
(…and the loop repeats for the next problem.)
```

**Explain every arrow (one line each):**

- Student → Problem: the student works on the problem the session assigned (`PY-C3-COUNT-DIV` first).
- Problem → Code Submission: the browser sends code text; all grading truth stays server-side.
- Code Submission → Code Execution: core-backend forwards code+tests to execution-service over HTTP.
- Code Execution → Failure Evidence: raw results are converted to a validated `EvidencePack`.
- Failure Evidence → Diagnosis: rules/LLM/fallback map evidence → one `C*-M**` ID.
- Diagnosis → Intervention: `level_for_history` (L1–L4) + curated type/skill produce student-facing guidance.
- Intervention → Retry: the student must re-attempt the same problem (no skipping by transfer).
- Retry → Transfer Problem: only a canonical PASS unlocks the isomorphic transfer variant.
- Transfer Problem → Verification: both outcomes are compared with the fixed decision table (§O).
- Verification → Learner Model Update: `run_closed_loop` records 2/2/1/0 attempts depending on outcome.
- Learner Model Update → Adaptive Next Action: fresh views feed `recommend_next_actions` → ranked list.
- Adaptive Next Action → (next) Student: the top recommendation + transfer unlock drive the UI.

> **Remember this:** *“Execute → evidence → diagnose → intervene → retry → transfer → verify →
> remember → adapt.”* If you can recite that with one sentence per arrow, you own Section A.

---

## B — Complete system architecture

### Mermaid architecture diagram

```mermaid
flowchart TB
    FE["Frontend<br/>(Next.js apps/web)"]
    CB["Core Backend :8000<br/>(orchestrator, owns state)"]
    AI["AI Service :8001<br/>(reasons only)"]
    EX["Execution Service :8002<br/>(executes only)"]
    SB["Docker Sandbox<br/>(student containers + helper)"]
    LM["Learner Model<br/>(learner_engine + SQLite)"]
    MF["Mastery Formula<br/>(packages/mastery)"]
    DG["Diagnosis Rules<br/>(ai-service rules + LLM + fallback)"]
    AD["Adaptive Engine<br/>(packages/adaptive R1-R8)"]
    VE["Verification Engine<br/>(packages/verification)"]
    PB["Problem Bank<br/>(problem-bank/ + loader)"]
    TX["Taxonomy<br/>(packages/taxonomy C1-C8)"]

    FE <--> CB
    CB <--> EX
    EX <--> SB
    CB --> AI
    CB <--> LM
    LM --> MF
    CB --> DG
    CB --> AD
    CB --> VE
    CB --> PB
    PB --> TX
    DG --> TX
    LM --> TX
    AD --> TX
    VE --> PB
```

**Who talks to whom (wiring observed in code):**

- Browser ↔ core-backend only (4 student endpoints; web never calls ai/execution directly —
  `apps/web/src/app/lib/api.ts` has exactly `createSession / submit / getJourney / getProblem`).
- Core-backend → execution-service over HTTP (`app/execution_client.py` via `httpx.post`
  to `EXECUTION_SERVICE_URL + /execute`; default `http://execution-service:8002`).
- Core-backend → ai-service: `[PARTIALLY IMPLEMENTED]` — the `student.py` flow imports the
  intervention builder **by loading the ai-service file directly in-process**
  (`_ensure_ai_package` alias-loads `services/ai-service/app/interventions.py`); the HTTP
  `POST /diagnose` endpoint exists but the student slice resolves diagnosis via the shared
  `packages/problem_bank/pipeline.py` helpers. Inferred from implementation: HTTP
  ai-service is available but not on the hot path of `POST /student/submissions`.
- Execution-service → Docker daemon (CLI subprocesses only; needs
  `/var/run/docker.sock` mounted — `docker-compose.yml`).
- Core-backend → SQLite (per-session in-memory DB in the prototype; file-backed
  `cognify_dev.db` default exists in `db.py` but the student slice does not use it — §K).

### Ownership table (memorize this — reviewers love it)

| Question | Answer | Evidence |
|---|---|---|
| Who **owns state**? | Core-backend (`StudentStore` + `learner_engine` + `repositories` + SQLAlchemy models). | `services/core-backend/app/{db,models,repositories,learner_engine,student}.py` |
| Who **only reasons**? | AI service (rules / LLM / fallback / gate / validator / interventions). It receives an `EvidencePack`, returns a `DiagnosisResult`. No DB imports. | `services/ai-service/app/*.py`; tests assert no DB/mastery imports. |
| Who **executes code**? | Execution-service (+ Docker sandbox). Core-backend never executes student code. | `services/execution-service/app/*`; `student._default_runner_factory` raises instead of executing locally. |
| Who **decides mastery**? | `packages/mastery/formula.py` (pure function) applied by `learner_engine.record_attempt`. | `formula.compute_mastery_update` — fixed constants (§L). |
| Who **decides adaptation**? | `packages/adaptive/policy.py` R1–R8 + `ranking.py` sort. Deterministic. | `policy.evaluate_all/evaluate_concept` (§N). |
| Who **verifies improvement**? | `packages/verification/engine.py` `verify_improvement` decision table. | PASS+PASS = `VERIFIED_IMPROVED` (§O). |
| Who is **allowed to write learner state**? | ONLY core-backend (`learner_engine.record_attempt` → `repositories` → session flush; caller commits). | `learner_engine.py` docstring; `repositories` never commits. |
| Who **must NOT write learner state**? | AI service / LLM, execution-service, frontend, adaptive & verification packages (all pure). | `db.py`: “AI service MUST NOT import this”; package tests assert no `sqlalchemy`/DB usage. |

### Design principle

> **“LLM semantic reasoning + deterministic learner state and adaptation.”**

- The **LLM may opine** (propose a misconception with explanation) but it may not decide,
  remember, or advance anything by itself. Its output must survive strict validation
  (schema + taxonomy grounding) and the confidence/grounding gate, or it is discarded.
- **State, numbers, and next steps are deterministic**: same evidence + same history ⇒ same
  mastery delta, same recurring flags, same ranked recommendations. Re-running the same
  computation gives the same answer (tests assert determinism everywhere).
- Concretely: `service.diagnose_pack` tries deterministic rules FIRST (bypassing the LLM
  entirely on a hit); `learner_engine` owns all writes; `policy`/`verification` are pure
  functions with no clock, randomness, I/O, or network.

> **Remember this:** *“The LLM suggests; the rules dispose. Nothing the model says becomes
> truth until validation, gating, execution evidence, transfer evidence, and the learner
> model agree.”*

---

## C — Complete repository map

### Tree (source files only; generated artifacts, `.venv`, `.next`, `__pycache__` omitted)

```text
cognify/
├── README.md                        # project bible (832 lines; Steps 0–20A status, limits)
├── requirements.txt                 # shared Python deps (fastapi, uvicorn, pydantic, httpx, sqlalchemy…)
├── Dockerfile                       # single shared image, ARG SERVICE_NAME/SERVICE_PORT
├── docker-compose.yml               # 4 services: core-backend, ai-service, execution-service, web
├── .env / .env.example              # local ports, URLs, LLM_* (empty = deterministic), DB placeholders
├── apps/
│   └── web/                         # Next.js 16 + React 19 + Tailwind 4 frontend
│       ├── package.json / next.config.ts / vitest.config.mts
│       ├── AGENTS.md / CLAUDE.md    # agent stubs only
│       └── src/
│           ├── app/                 # routes: / /learn /practice /progress /history + lib/api.ts
│           └── components/          # practice.tsx, session.tsx, cards.tsx, layout.tsx, ui.tsx
├── services/
│   ├── core-backend/app/            # orchestrator + learner state owner
│   │   ├── main.py / student.py / execution_client.py
│   │   ├── learner_engine.py / closed_loop.py
│   │   └── db.py / models.py / repositories.py
│   ├── ai-service/app/              # diagnosis brain (no state)
│   │   ├── main.py / service.py / rules.py / fallback.py / gate.py / validator.py
│   │   ├── prompt.py / llm_client.py / config.py / models.py / interventions.py
│   └── execution-service/app/       # code runner (no state, no intelligence)
│       ├── main.py / models.py / evaluator.py
│       ├── runners.py / python_runner.py / java_runner.py / sandbox.py
├── packages/                        # pure deterministic libraries (no DB/LLM/network)
│   ├── taxonomy/                    # C1–C8 concepts, 48 misconceptions, 5 cross-cutting, query API
│   ├── mastery/                     # formula.py (owns mastery math) + weakness.py (R1/R2/R3)
│   ├── adaptive/                    # policy.py (R1–R8) + ranking.py + models.py + reasons.py
│   ├── verification/                # engine.py (decision table) + models.py + reasons.py
│   ├── evidence/                    # EvidencePack models + builder + examples
│   ├── problem_schema/              # Problem/TestCase models + examples
│   └── problem_bank/                # loader.py + pipeline.py + journey.py (orchestration helpers)
├── problem-bank/python/             # 24 problem JSONs + 24 _canonical.py reference solutions
├── docs/                            # [was empty] this handbook lives here
├── infra/                           # [empty, reserved] no infra-as-code currently
└── tests/                           # [empty, reserved] tests live next to each service/package
```

> `docs/`, `infra/`, `tests/` at repo root are **empty directories** (verified 2026-09-20).
> Real tests live in `services/*/tests/` and `packages/*/tests/`.

### What each directory is for

| Directory | Responsibility | Status |
|---|---|---|
| `apps/web` | Student-facing UI: session bootstrap, problem display, code editor, result/feedback rendering, progress. No intelligence; 4 typed wrappers over core-backend. | `[IMPLEMENTED]` (C3-live; history page is an honest empty state) |
| `services/core-backend` | Product API + orchestration + the ONLY learner-state writer. Owns sessions, problem resolution, execution calls, evidence/diagnosis wiring, mastery recording, verification + adaptive calls. | `[IMPLEMENTED]` (prototype persistence limits) |
| `services/ai-service` | Diagnosis brain: deterministic C3 rules → LLM → fallback, with strict validator + confidence/grounding gate + intervention builder. Never touches the DB. | `[IMPLEMENTED]` (rules C3-only; LLM path exists but default env disables it) |
| `services/execution-service` | Untrusted-code runner: validates request, compiles (Java), runs each test in a Docker sandbox, aggregates `PASSED/FAILED/COMPILE_ERROR/RUNTIME_ERROR/TIMEOUT`. | `[IMPLEMENTED]` (Python solid; Java wired with a double-compile inefficiency — §G) |
| `packages/taxonomy` | Single source of truth for concepts C1–C8, misconceptions, prerequisites, language scope. Everything else validates against it. | `[IMPLEMENTED]` |
| `packages/mastery` | The mastery formula + bands + trend + recurring/improvement predicates. Pure math, no I/O. | `[IMPLEMENTED]` |
| `packages/adaptive` | Deterministic next-action policy R1–R8 + ranking + reason templates. Reads mastery, never computes it. | `[IMPLEMENTED]` |
| `packages/verification` | PASS/FAIL → improvement-verdict decision table. Never executes, never writes. | `[IMPLEMENTED]` |
| `packages/evidence` | `EvidencePack` schema + builder (observed evidence only) + secret scrubbing. | `[IMPLEMENTED]` |
| `packages/problem_schema` | `Problem`/`TestCase` schema + validation (difficulty 1–5, roles, misconception binding). | `[IMPLEMENTED]` |
| `packages/problem_bank` | Bank loader + pipeline helpers (execute → student view → evidence → diagnose → verify) + scripted C3 journey. Reuses service/package APIs; duplicates none. | `[IMPLEMENTED]` |
| `problem-bank/` | Data: 24 Python problem JSONs (2 public + 3 hidden tests each) + reference solutions. | `[IMPLEMENTED]` (Python only) |
| `infra/` | Reserved. | `[PLANNED / NOT IMPLEMENTED]` (compose + Dockerfile cover current needs) |
| `docs/` | This handbook (previously empty). | `[IMPLEMENTED]` (by this document) |

---

## D — File-by-file responsibility map

File classes: **CORE FILE** (must know for viva) · **IMPORTANT SUPPORT FILE** (know its job) ·
**TEST FILE** · **CONFIGURATION FILE** · **DATA FILE** · **REFERENCE ONLY** (generated/stub).

### D.1 Core-backend (`services/core-backend/app/`) — all CORE FILE except `__init__.py`

| File | Responsibility | Called By | Calls | Important Functions/Classes | Why It Exists |
|---|---|---|---|---|---|
| `main.py` | App factory: `FastAPI(title="cognify-core-backend", version="0.2.0")`, CORS from `STUDENT_CORS_ORIGINS` (default `http://localhost:3000`), mounts `GET /health` + student router. Injectable `runner_factory/llm_client/store` for tests. | `uvicorn app.main:app`; tests via `create_app(...)`. | `student.create_student_router`. | `create_app(*, runner_factory, llm_client, store)`, `health()`, `_cors_origins()`. | Single entrypoint; keeps prod wiring separate from test injection. |
| `student.py` (~1150 lines) | Student vertical slice: 7 endpoints (4 Step-16 loop endpoints + 3 Step-20B read-only views), server-side problem resolution, execution dispatch, evidence→diagnosis→record→intervene→verify→recommend orchestration. Contains NO intelligence (delegates to Steps 5–15 APIs; Step 20B additionally delegates per-concept state to taxonomy + learner-engine views, the next action to `recommend_next_actions`, history to existing attempt events, the catalog to `load_all_problems`). C3 constants `CANONICAL_ID=PY-C3-COUNT-DIV`, `TRANSFER_ID=…-TRANSFER`, `PROBE_ID=PY-C3-LOOP-MISCONCEPTION`, caps `MAX_CODE_CHARS=100_000`, `TIMEOUT_SECONDS=5.0`, view truncation `2_000`, history `DEFAULT_LIMIT=20/MAX_LIMIT=50`, display-only `CONCEPT_GROUPS` (taxonomy has no group field). | `main.create_app`; browser via HTTP. | `execution_client`, `problem_bank.loader/pipeline`, `learner_engine`, `closed_loop`, `adaptive`, `verification`, ai `interventions` (alias-loaded in-process). | `create_student_router`, `StudentStore` (process-local dict + per-session in-memory SQLite), `_resolve_problem`, `_execute`, `_submit_transfer`, `problem_view/execution_view/diagnosis_view/intervention_view/recommendation_view/verification_view`, `_journey_state`, `_catalog`, `_concept_card/_next_action_view/_full_problem_catalog/_human_issue_summary/_history_feedback/_safe_description` (Step 20B view helpers). | The one file that turns “HTTP request” into “learning-loop step”. Spoofing/hidden-test/redaction guards live here (20B adds MID/iso/mastery-float/evidence-ref redaction + bank-description MID scrub). |
| `execution_client.py` | ONLY production execution integration: builds payload, `httpx.post(EXECUTION_SERVICE_URL + /execute)`, deep-validates response, maps failures (unreachable/5xx → `ExecutionServiceUnavailable` → HTTP 503; malformed → `BadResponse` → 502). Never executes locally, never imports Docker. | `student._execute` (production branch). | `httpx` → execution-service. | `build_payload`, `validate_response`, `execute_problem`, `get_base_url`; `VALID_STATUSES={PASSED,FAILED,COMPILE_ERROR,RUNTIME_ERROR,TIMEOUT}`. HTTP timeout = `max(10, timeout*(n_tests+1)+10)`. | Keeps the orchestrator honest: sandbox outage fails closed instead of silently grading locally. |
| `learner_engine.py` (1024 lines) | Learner Model + Mastery owner. ONLY writer of learner state. `record_attempt` validates → computes mastery via `packages.mastery` → updates counters → recurring evaluation → improvement sweep → appends `attempt/diagnosis/mastery_transition(+recurring_*)` events. Read views `get_concept_view/get_misconception_view`, explainer `explain_mastery`, DTO exporter `snapshot_for_evidence`. | `student.py`, `closed_loop.run_closed_loop`, tests. | `repositories`, `packages.mastery.formula/weakness`, `packages.evidence.models`, `problem_schema.normalize_variant_role`. | `ensure_concept_state` (fresh → `INITIAL_MASTERY=0.20/novice/unknown`), `record_attempt(...)` (full signature §K), `get_concept_view`, `get_misconception_view`, `explain_mastery`, `snapshot_for_evidence`. | Dibs on state: AI must never write here (`db.py` forbids AI imports). All mastery/counter/flag/event mutations funnel through this file. |
| `closed_loop.py` (953 lines) | Verification → learner → adaptive orchestration: `VerificationResult → plan_records → record_attempt → views → recommend_next_actions → ClosedLoopResult`. Pure planning (`plan_records`: INCOMPLETE→0, NOT→1, SURFACE/VERIFIED→2 records) + `run_closed_loop` (validates journey/user/track match; INCOMPLETE mutates nothing). | `student._submit_transfer`; tests. | `learner_engine`, `adaptive`, `verification`, `repositories`. | `ClosedLoopContext` (frozen, validated), `AttemptPlan`, `plan_records`, `RecordedAttempt`, `LearnerStateSnapshot`, `ClosedLoopResult`, `run_closed_loop`, `build_closed_loop_reason`. Constants `ORIGINAL_KIND=original_retry/TRANSFER…`, `EXECUTION_STATUS_FOR_OUTCOME` map. | Separates “what should be recorded” (pure plan) from “record it” (DB writes) so the mapping is testable without a database. |
| `models.py` | SQLAlchemy schema ONLY (docstring: “Mastery is STORED here, never calculated”). 6 tables: `users, journeys, learner_concept_states, misconception_counters, recurring_flags, learner_events` with CHECK vocabularies generated from `packages.taxonomy` (`concept_id IN (C1..C8)`, `language_track IN (python,java)`), `mastery ∈ [0,1]`, non-negative counters, FK CASCADE, UNIQUE per (journey,concept[,misconception]). | `db.init_db`, `repositories`, `learner_engine`, tests. | `packages.taxonomy` (vocab), `db.Base`. | `User/Journey/LearnerConceptState/MisconceptionCounter/RecurringFlag/LearnerEvent`. Raw-create default mastery `0.0` (normalized to `0.20` by `ensure_concept_state`). | One schema definition so taxonomy, problem schema, and DB can never disagree on concept/language IDs. |
| `db.py` | Engine/session/Base config ONLY. Default `sqlite:///./cognify_dev.db` (overridable `DATABASE_URL`), SQLite FK pragma ON, `session_scope` (commit-on-success/rollback/close). | `StudentStore.create`, tests. | `sqlalchemy` only. | `Base`, `get_database_url/get_engine/get_session_factory/session_scope/init_db`. | Isolates connection policy so AI service can be banned from importing it (separation of powers). |
| `repositories.py` (564 lines) | CRUD/reads ONLY with taxonomy normalization (`strip().lower()/upper()`, `is_valid_*`, `misconception_belongs_to`, journey-of-user checks, strict `type(x) is int` rejecting bools). Never calculates mastery; `update_concept_state` stores given values; `flush()` but never `commit` (caller owns the transaction). | `learner_engine`, `closed_loop`, `StudentStore.create`, tests. | `models`, `packages.taxonomy`. | `create_user/get_user`, `create_journey/get_active_journey/set_journey_active`, `get_or_create_concept_state/update_concept_state`, `get_or_create_counter/increment_counter/set_counter_active`, `set_recurring_flag/get_flag`, `create_event/list_events_for_journey`. | Validation bulkhead: every write is normalized + belonging-checked before it touches the DB. |
| `__init__.py` | `sys.path` bootstrap so `import packages.*` works when launched from the service dir. No logic. | Import time. | `pathlib/sys`. | — | REFERENCE ONLY (support). |

### D.2 AI service (`services/ai-service/app/`)

| File | Class | Responsibility | Called By → Calls | Key contents |
|---|---|---|---|---|
| `main.py` | CORE | HTTP API: exactly 2 endpoints — `GET /health`, `POST /diagnose` (validates `EvidencePack`, resolves LLM client, delegates to `service.diagnose_pack`). Missing key ⇒ fallback-only, never crash. | uvicorn/tests → `service`. | `create_app(llm_client/llm_client_factory)`, `diagnose()`, `_default_client_from_env()`. |
| `service.py` | CORE | Orchestrator order: **rules FIRST → LLM → fallback**. Rule hit returns `source="fallback"` with `Rule <ID>:` prefix (bypasses LLM, `client.calls == []` in tests). LLM path needs validator + gate to pass for `source="llm"`. Any failure → `fallback_diagnose`. | `main.diagnose`, pipeline `diagnose_evidence` → `rules/prompt/llm_client/validator/gate/fallback`. | `diagnose_pack(pack, client, *, min_confidence=0.50)`, `_parse_llm_json` (markdown-fence tolerant). |
| `rules.py` | CORE | 2 deterministic C3 evidence rules (Step 15), each self-checked through validator + gate before firing; else abstain (`None`). | `service` → `validator/gate/taxonomy/ast`. | `RULE_C3_RANGE_BOUNDARY_EXCLUSION → C3-M01` (code `range(..., len(X)-1)` via AST + EVERY failed test `actual == expected-1` + ≥1 pass); `RULE_C3_RANGE_EXCLUSIVITY → C3-M05` (code `range(<int>, <bare-name>)` + EVERY failed test `actual == expected-n`); `RULE_CONFIDENCE=0.70`; `try_rule_diagnosis`. Full trigger tables §I. |
| `fallback.py` | CORE | Deterministic fallback classifier: `score = 0.30 + (0.20 if recurring) + min(count*0.05, 0.15)`; winner = highest score, ties → higher count → recurring → smallest ID. Confidence capped `0.55` (`0.40` if `failed_count==0`). | `service` (last resort). | `fallback_diagnose`, `BASE_CONFIDENCE/RECURRING_BONUS/PER_OCCURRENCE_BONUS/MAX_OCCURRENCE_BONUS/PASSED_CONFIDENCE_CAP/FALLBACK_CONFIDENCE_CAP`. `Fallback: …` explanation. |
| `gate.py` | CORE | Trust gate: reject if `confidence < 0.50` OR evidence refs lack failure grounding (`failed_test:/test:/code/stdout/stderr/expected_output/actual_output`). `failed_count==0` packs auto-pass grounding. | `service`, `rules._checked` → none (pure). | `MIN_ACCEPT_CONFIDENCE=0.50`, `confidence_grounding_gate`, `_is_failure_grounded`. |
| `validator.py` | CORE | Strict validator: must be dict with EXACTLY the 5 keys; concept must equal pack; MID must be a pack candidate + taxonomy-valid + belonging; confidence numeric ∈ [0,1] (bool rejected); explanation 10–500 chars; refs 1–8, each bare-or-`failed_test/test/candidate/history/recurring`-prefixed and resolvable; no duplicates. | `service`, `rules` → `taxonomy`. | `validate_llm_diagnosis`, `DiagnosisValidationError`, `REQUIRED_KEYS`. |
| `interventions.py` | CORE | Deterministic intervention builder (NOT generative): level from history only (`L4` if recurring+count≥3, `L3` if recurring, `L2` if count≥1, else `L1`); type/skill curated (`C3-M01→BOUNDARY_CHECK/loop-boundary-checks`, `C3-M05→TRACE_LOOP/range-stop-semantics`, else `TARGETED_HINT`/taxonomy name). Rejects concept mismatch / unknown MID / non-candidate MID. | `student` (alias-loaded), pipeline → `taxonomy`. | `level_for_history`, `build_intervention`, `Intervention`, `LEVEL_NAMES={L1:NUDGE,L2:MICRO_LESSON,L3:SCAFFOLD,L4:RETEACH}`. |
| `prompt.py` | IMPORTANT SUPPORT | Deterministic `{system, user}` prompt renderer: system lists 7 rules (candidate-only, concept equality, JSON-only, no DB/mastery/hints/roadmap); user embeds pack JSON (`sort_keys=True`) + candidate list + decisive test. Same pack ⇒ same prompt. | `service` → `evidence`. | `SYSTEM_PROMPT_TEMPLATE`, `DIAGNOSIS_JSON_SHAPE`, `build_diagnosis_prompt/messages`. |
| `llm_client.py` | IMPORTANT SUPPORT | Provider abstraction; diagnosis never hands the LLM any DB. `OpenAICompatibleLLMClient` posts `{model, messages, temperature:0.0, response_format:{json_object}}` to `{base}/chat/completions`; 401/403/429 → `LLMUnavailableError` (⇒ fallback). `Mock/Unavailable` for tests. | `service/main` → `httpx`. | `BaseLLMClient/MockLLMClient/UnavailableLLMClient/OpenAICompatibleLLMClient`, `LLMError/LLMUnavailableError`. |
| `config.py` | IMPORTANT SUPPORT | `LLM_*` env config: providers `"" / openai / mock`; defaults `model=gpt-4o-mini`, `base=https://api.openai.com/v1`, `timeout=30.0 ∈ [1,120]`; `openai` requires `LLM_API_KEY`. `enabled = provider != ""`. | `main` → `os.environ`. | `LLMConfig`, `get_llm_config`, `SUPPORTED_PROVIDERS`. Default env has `LLM_PROVIDER=` (empty ⇒ deterministic mode). |
| `models.py` | IMPORTANT SUPPORT | Shape validation only: `Diagnosis` (concept/MID/conf/explanation 10–500/refs 1–8 unique ≤200 chars, `extra=forbid`, IDs upper-normalized), `DiagnosisResult` (+`source: llm|fallback`), `DiagnosisRequest`. | `main/service/validator`. | `MAX/MIN_EXPLANATION_CHARS=500/10`, `MAX/MIN_EVIDENCE_REFS=8/1`, `DiagnosisSource`. |
| `__init__.py` | REFERENCE | `sys.path` bootstrap. | Import time. | — |

### D.3 Execution service (`services/execution-service/app/`)

| File | Class | Responsibility | Called By → Calls | Key contents |
|---|---|---|---|---|
| `main.py` | CORE | HTTP API: `GET /health`, `GET /languages → {python,java}`, `POST /execute → 200 ExecutionResult / 422 validation / 503 no-Docker`. `create_app(runner_factory=None)` injectable for tests. | uvicorn/tests → `evaluator`. | `execute()`, `default_runner_factory` (python→`PythonRunner`, java→`JavaRunner`). |
| `models.py` | CORE | Request/response shapes + limits: `MAX_CODE_CHARS=100_000`, `MAX_TESTS_PER_REQUEST=50`, `timeout ∈ [1.0,30.0]` default `5.0`; `language ∈ {python,java}`; statuses `PASSED/FAILED/COMPILE_ERROR/RUNTIME_ERROR/TIMEOUT`. | `main/evaluator` → pydantic. | `ExecutionRequest/TestCaseInput/ExecutionResult/TestCaseResult/ExecutionStatus`. |
| `evaluator.py` | CORE | Runs all tests via runner: `compile()` short-circuit → per-test `run_single` → output normalization (CRLF→LF, rstrip lines, strip) → aggregate (`TIMEOUT` beats `RUNTIME_ERROR` beats `FAILED`; decisive = first failure; top-level mirrors decisive; times summed). | `main` → `runners`. | `evaluate()`, `normalize_output()`, `_compile_error_result()`. |
| `sandbox.py` | CORE | Docker isolation (487 lines): availability probe (`docker info`), helper container populates a named volume (`python:3.11-slim`, `--network none`, 30s), student container (`--rm --network none --memory 256m --memory-swap 256m --cpus 1.0 --pids-limit 128 -v vol:/workspace -w /workspace -i image`), timeout→kill→`TIMEOUT` result, `finally volume rm`. Fail-closed when Docker missing. No `shell=True`/`eval`/`env` forwarding. | `python_runner/java_runner` → `docker` CLI via `subprocess.run`. | `DockerSandboxRunner.run/build_command`, `docker_available`, `SandboxResult/SandboxUnavailableError`, `DEFAULT_MEMORY=256m/DEFAULT_CPUS=1.0/DEFAULT_PIDS_LIMIT=128`, filename guard (no absolute/`..`). |
| `runners.py` | IMPORTANT SUPPORT | `BaseRunner` ABC: `compile() → str\|None` (default `None` = interpreted), abstract `run_single() → RunResult`. | `evaluator` → `sandbox`. | `BaseRunner`, `RunResult`. |
| `python_runner.py` | IMPORTANT SUPPORT | Python mapping: image `python:3.11-slim`, file `solution.py`, cmd `["python","/workspace/solution.py"]`; no `compile` override ⇒ `SyntaxError` surfaces as `RUNTIME_ERROR`. | `main/evaluator` → `sandbox`. | `PythonRunner`, `PYTHON_IMAGE/SOLUTION_FILENAME/RUN_COMMAND`. |
| `java_runner.py` | IMPORTANT SUPPORT | Java mapping: image `eclipse-temurin:17-jdk`, `Main.java`/`public class Main`; `compile()` runs `javac` once, but `run_single()` re-runs `javac && java` per test (double-compile inefficiency — §G). | `main/evaluator` → `sandbox`. | `JavaRunner`, `COMPILE_COMMAND/RUN_COMMAND`. `[PARTIALLY IMPLEMENTED]` for efficiency (works, wasteful). |
| `demo.py` | REFERENCE | Simulated demo with fakes; no Docker. | Manual runs. | `FakeSandboxRunner` (note: its `RUN_COMMAND` does not match production Java argv). |
| `__init__.py` | REFERENCE | Package marker. | — | — |

### D.4 Packages (all deterministic, stdlib-only — CORE unless noted)

| File | Responsibility | Called By → Calls | Key contents |
|---|---|---|---|
| `taxonomy/concepts.py` | 8 concepts C1–C8 in order with topics + prerequisites. | `api/models/repositories/adaptive/*` → none. | `Concept`, `CONCEPTS`, `CONCEPT_IDS`. Chain: C1→C2→C3→C4→{C5,C6,C7}→C8 (§J). |
| `taxonomy/errors.py` | 48 misconceptions (6/concept: 4 shared + 1 python-only + 1 java-only) + 5 cross-cutting `X-*`. Each has name/description/languages/typical_signal. | `api/validator/interventions/evidence` → none. | `Misconception/CrossCuttingError`, `SUPPORTED_LANGUAGES=(python,java)`. |
| `taxonomy/api.py` | Pure query/validation (`strip().upper()` tolerant). | Everyone → `concepts/errors`. | `list_concepts/is_valid_concept/get_concept/list_misconceptions/is_valid_misconception/misconception_belongs_to/…`. **Support.** |
| `mastery/formula.py` | SOLE mastery math owner (pure). Constants + bands + severity + `compute_mastery_update` + trend/rate helpers. | `learner_engine` → none. | §L verbatim. |
| `mastery/weakness.py` | Recurring R1/R2/R3 + improvement predicates (pure). | `learner_engine` → none. | `RECENT_WINDOW=5/RECENT_THRESHOLD=2/HISTORICAL_THRESHOLD=3/VARIANT_THRESHOLD=2/IMPROVEMENT_WINDOW=3`; `check_recurring/recent_occurrence_count/isomorphic_variant_count/has_improved`. **Support but viva-critical.** |
| `adaptive/models.py` | Typed I/O: `ActionType×6`, `ReasonCode×9`, `ConceptState/MisconceptionState/CurriculumInfo/ProblemInfo/Recommendation` (frozen; `from_learner_view` tolerates Step-18 richer views). | `policy/ranking/learner_engine/closed_loop` → `taxonomy`. | Enums + dataclasses; `VALID_TRENDS/BANDS/VARIANT_ROLES`. |
| `adaptive/policy.py` | Deterministic R1–R8 policy assigning integer priorities (sorting lives in `ranking.py`). | `learner_engine/closed_loop` → `models/reasons`. | §N verbatim (thresholds 0.60/0.40/0.80, hint 0.50, transfer ≥2 attempts, bases 100/80/70/50/40/30, boosts +15/+10/+10). |
| `adaptive/ranking.py` | Pure sort `(-priority, concept, action, problem, reason_code, reason)`. | `closed_loop/learner_engine` → none. | `rank_key/rank_recommendations`. **Support.** |
| `adaptive/reasons.py` | Human-readable reason templates (deterministic strings). | `policy` → none. | `prerequisite/low_mastery/recurring/emerging/proficient/transfer_ready/challenge_ready/declining/hint_dependence_reason`. **Support.** |
| `verification/models.py` | Scope + outcome vocabularies; frozen `VerificationAttempt/Context/Result` with cross-field validation (concept/track/group agreement, outcome↔booleans, reason↔outcome). `intervention_level` never influences verdict. | `engine/closed_loop/student` → none. | `ExecutionOutcome×5/VerificationOutcome×4/ReasonCode×5`, `is_pass` (only PASS passes). |
| `verification/engine.py` | Decision table + evidence builder + `to_learner_evidence` slice. Pure. | `closed_loop/student/pipeline` → `models/reasons`. | `verify_improvement/build_evidence/to_learner_evidence` (§O). |
| `verification/reasons.py` | 5 reason templates; verified text **disclaims mastery** (“verified-improvement evidence, not concept mastery”). | `engine` → none. | `build_reason`. **Support.** |
| `evidence/models.py` | `EvidencePack` schema: observed-only (`evidence_kind="observed"`, `confirmed=None`, `inference_status="pending-diagnosis"`), code ≤100k verbatim, candidates ≥1 unique same-concept, failed pointers mirror first failed test, history filtered same-concept, events ≤10 same-concept, secret-key fragments rejected. | `builder/service/learner_engine` → `taxonomy`. | `EVIDENCE_SCHEMA_VERSION=1.0`, `VALID_EXECUTION_STATUSES×5`, `FailedTestEvidence/MisconceptionCandidate/…/EvidencePack`. |
| `evidence/builder.py` | Builds packs: validates language agreement (problem==exec==learner), enriches candidates via taxonomy in problem order, copies execution raw (failed tests only, in order), filters history, trailing-slice + sanitizes events. | `student/pipeline/learner_engine` → `models`. | `build_evidence_pack`, `sanitize_metadata` (drops password/secret/token/… recursively). **Support.** |
| `evidence/examples.py` | Canonical worked example (off-by-one `range(1,n)`, FAILED 79ms, C3 snapshot mastery 0.35…). | Tests/docs → `models`. | `make_example_evidence_pack/EXAMPLE_*`. **Support.** |
| `problem_schema/models.py` | `TestCase` (ID pattern `^[A-Za-z0-9][A-Za-z0-9._-]*$`) + `Problem` (concept UPPER-known, language lower py/java, difficulty int 1–5 bool-rejected, non-empty texts, ≥1 constraint, starter verbatim, ≥1 public tests, IDs unique across public+hidden, group+role, ≥1 unique belonging misconception). | `loader/bank JSONs` → `taxonomy`. | `Problem/TestCase/all_tests/is_valid_variant_role/is_valid_difficulty`, `VALID_VARIANT_ROLES=(canonical,transfer,remedial)`. |
| `problem_schema/examples.py` | 3 data-only examples incl. transfer sharing group `ISO-C3-SUM-EVENS`. | Tests → `models`. | `PY-C3-001/JAVA-C2-001/PY-C3-002`. **Support.** |
| `problem_bank/loader.py` | JSON→`Problem` (`load_problem_file/list_problem_ids/load_all_problems/load_problem`, sorted discovery, duplicate-ID error). | `student/pipeline/journey` → `problem_schema`. | `DEFAULT_BANK_DIR=<root>/problem-bank/python`. **Support.** |
| `problem_bank/pipeline.py` | Step-12 orchestration reusing Steps 5/6/7/10/11 (alias-loads hyphenated service apps); scripted runners for tests; `to_student_view` (hidden `expected_output→None` + `hidden_redacted`); `attempt_from_execution` ONLY from actual results; `EXECUTION_TO_VERIFICATION_OUTCOME` map. | Tests/`student` → exec/ai/evidence/verification/closed_loop. | `execute_problem/result_to_dict/execution_status_str/to_student_view/default_learner_snapshot/build_pack_for_submission/diagnose_evidence/verification_outcome_for/attempt_from_execution/plan_records_for_context`. **Support.** |
| `problem_bank/journey.py` | Step-14 scripted C3 journey (A wrong→B fixed→C transfer ⇒ `VERIFIED_IMPROVED`); orchestration only, no intelligence. | Tests → loader/pipeline/learner/adaptive/verification/closed_loop. | `CANONICAL_ID/TRANSFER_ID/PROBE_ID`, `SUBMISSION_A/B/C_*`, `run_learning_journey`, `LearningJourneyResult`. **Support.** |

### D.5 Frontend (`apps/web/src/`) — CORE files for the demo flow

| File | Class | Responsibility | Calls | Key contents |
|---|---|---|---|---|
| `app/lib/api.ts` | CORE | Typed wrappers over core-backend ONLY. `BASE_URL = NEXT_PUBLIC_CORE_BACKEND_URL ?? http://localhost:8000`. Exactly 7 fns + `ApiError/friendlyError` (0→“Backend unreachable”, 409→finish-current, 503→execution-unavailable). | `fetch` → `/student/*`. | `createSession/submit/getJourney/getProblem/getConcepts/getHistory/getProblems`; views `Problem/Execution/Diagnosis(confidence_label likely\|possible\|uncertain)/Intervention/Recommendation/Verification/JourneyState/Submission/Session/ConceptCard/NextActionView/HistoryItem/HistoryResponse/ProblemCatalogEntry/ProblemsResponse`. |
| `app/practice/page.tsx` | CORE | Practice screen state machine: `MAX_CODE_CHARS=100_000` (mirrors backend), `requestId` guard (newest submit wins), starter-code init, `submit/continueToTransfer/retry`, `role="alert"` + `aria-live="polite"`. | `api`, `components/practice`. | `PracticePage`, `submit()`, `continueToTransfer()`. |
| `components/practice.tsx` | CORE | `ProblemPanel` (never shows tests internals beyond inputs policy), `CodeEditor` (textarea + Cmd/Ctrl+Enter + Running…), `ResultPanel` (PASSED/transfer-verified/FAILED/error branches), `FailedFeedback` (passed X/Y, TestList w/ hidden redaction, certainty heading, explanation, InterventionCard, Retry), `RecommendationList` (top 3), `DebugDetails` (raw IDs only with `?debug=1`). | `lib/copy` (`stripCodes/humanizeReason/isDebugMode`). | All above; `verified = outcome==="VERIFIED_IMPROVED"`. |
| `components/session.tsx` | CORE | Throwaway session: `localStorage["cognify.session_id"]`, `boot()` (fresh or `getJourney`+enrich; 404→fresh “session expired”), `refresh/restart/startFresh`, `SessionProvider/useSession`, `FreshSessionNote`. | `api`. | `STORAGE_KEY`, `boot/startFresh/refresh/restart`. |
| `app/page.tsx` | IMPORTANT | Home “what next”: `ContinueCard` (journey/session state) + `NextStepCard` (backend `next_action` first, journey recommendation fallback) + best-effort “Where you stand” (started-concept levels) + “Recent activity” (last history items); enrichment failures degrade to journey-only content. | `api/session/cards`. | `HomePage`. |
| `app/learn/page.tsx` | IMPORTANT | Roadmap from `GET /student/concepts`: all 8 concepts grouped by backend `group`, live band/trend/attempts per concept, honest “Not started yet” for zero-attempt concepts; loading + error + retry states. | `api`, `lib/copy` (`trendLabel`). | `LearnPage`. |
| `app/progress/page.tsx` | IMPORTANT | Learner overview from `GET /student/concepts`: level labels (never raw numbers), trend/attempts/recent/transfer/hint-reliance in plain language, “current level” vs `mastery_claim` kept distinct, adaptive `next_action` via `NextStepCard`; honest empty + error states. | `api`, `cards`, `lib/copy`. | `ProgressPage`. |
| `app/history/page.tsx` | IMPORTANT | Real history from `GET /student/history`: problem/concept titles, human outcome + feedback, verified-improvement flags; loading + error + honest empty states; no raw codes. | `api`, `lib/copy` (`outcomeLabel/stripCodes`). | `HistoryPage`. |
| `components/cards.tsx` / `layout.tsx` / `ui.tsx` | SUPPORT | `ContinueCard/NextStepCard/FreshSessionNote`; nav Home/Learn/Practice/Progress/History + “current language: Python”; primitives `Card/PageHeading/PrimaryButton/Alert/Loading/EmptyState/LevelLabel/Mark`. | — | — |
| `app/lib/copy.ts` / `concepts.ts` | SUPPORT | Humanization: `stripCodes` (C3-M01→“this idea”, SCREAMING_SNAKE→“this step”), `humanizeReason`, `isDebugMode`; static 8-concept/6-group map (NOT learner state). | — | — |

### D.6 Config / data / tests

| File | Class | Notes |
|---|---|---|
| `README.md` | REFERENCE ONLY (but viva-critical) | Declares Steps 0–20B done; C3 slice; rules; ports; 24 problems; limits; test counts; prototype constraints. |
| `docker-compose.yml` / `Dockerfile` / `requirements.txt` / `.env(.example)` / `services/*/.env.example` | CONFIGURATION | §F/§G details; single shared image; `EXECUTION_SERVICE_URL/AI_SERVICE_URL` wiring; `LLM_PROVIDER=` empty default; `DATABASE_URL` prototype placeholder (asyncpg URL incompatible with sync engine — reserved). |
| `problem-bank/python/*.json` (24) + `*_canonical.py` (24) | DATA | Schema §Q; canonical files are DATA ONLY (“NEVER executed by the pipeline”). |
| `services/*/tests/*.py`, `packages/*/tests/*.py`, `apps/web/**/__tests__/*` | TEST | Step-wise regression (smoke, student flow, closed loop, execution client, learner intelligence/model, mastery, diagnosis, step15, execution, evidence, schema, taxonomy, verification, bank steps 12/13/14/19, frontend vitest). |
| `apps/web` configs (`next.config.ts` empty, `postcss`, `eslint`, `tsconfig`, `vitest.config.mts`) | CONFIGURATION | Standard Next 16 / Tailwind 4 / Vitest jsdom setup. |
| `apps/web/AGENTS.md`, `CLAUDE.md` | REFERENCE ONLY | Agent stubs, no product behavior. |

### Spotlight: `services/core-backend/app/learner_engine.py` (`record_attempt` deep-dive — viva favorite)

- **Why it exists:** it is the single gate through which every learner-state mutation passes, so
  mastery/counters/flags/history can never diverge. AI, adaptive, and verification code cannot
  write; they can only ask this file to record a validated attempt.
- **What it receives:** `session, user_id, journey_id, concept_id, problem_id,
  isomorphic_group_id, variant_role, passed: bool, execution_status, diagnosed_misconception_id?,
  diagnostic_confidence?, hint_used: bool, evidence_refs?, is_transfer?`.
- **What it validates:** concept + misconception normalization and belonging; non-empty
  problem/iso IDs; variant role; bool types; evidence-ref dedup; confidence ∈ [0,1];
  `passed`⇔`PASSED` agreement both directions; journey-of-user; transfer flag vs role agreement.
- **What it updates:** `LearnerConceptState` (mastery via formula, band, trend, attempt/success/
  hint/transfer counters) + `MisconceptionCounter` (+1 + reactivate) + `RecurringFlag`
  (only on False→True) + deactivations for improved misconceptions + append-only events.
- **What it returns:** `{transition, concept_view, misconception_view?, is_recurring,
  recurring_reason, improved_ids}` — everything the caller needs to respond without re-querying.
- **How mastery changes:** `prior_rate` = trailing-5 pass rate (0.5 if none) →
  `compute_mastery_update(previous, passed, status, hint, transfer, prior_rate)` → clamp+round4.
- **How evidence is attached:** `evidence_refs` (deduped) stored on the `attempt` event; diagnosis
  stored on a `diagnosis` event; the transition event stores prev/new/delta/reason/bands/trend/flags.
- **How recurring is detected:** histories excluding current + current appended explicitly →
  `recent_occurrence_count` + `isomorphic_variant_count` → `check_recurring` → flag + event.
- **Who calls it:** `student.py` (FAILED/error submissions) and `closed_loop.run_closed_loop`
  (verification-driven records). Nobody else may mutate learner tables.

---

## E — End-to-end student journey (realistic C3 run)

> Worked example used across tests: canonical `PY-C3-COUNT-DIV` (“Count Divisible Numbers”),
> transfer `PY-C3-COUNT-DIV-TRANSFER` (“Count Cold Days”), probe `PY-C3-LOOP-MISCONCEPTION`.
> Buggy submission: `for i in range(len(nums) - 1)` (drops last element); fixed: `for x in nums`.

| # | Step | INPUT → PROCESS → OUTPUT → NEXT |
|---|---|---|
| 1 | Student starts a session. | IN: click/open app. PROC: `SessionProvider.boot()` reads `localStorage`; none ⇒ `api.createSession()`. OUT: `{session_id, problem(canonical)}`. NEXT: editor shows starter code. |
| 2 | Backend creates/resolves session. | IN: `POST /student/sessions {}`. PROC: track must be `python` (else 422); `StudentStore.create` builds in-memory SQLite + user + journey + token. OUT: session + `problem_view(canonical)` (no tests/answers). NEXT: frontend stores `session_id`. |
| 3 | Student receives problem. | IN: session. PROC: `_resolve_problem` loads `PY-C3-COUNT-DIV` from bank; role/language checked. OUT: title, statement, constraints, I/O formats, starter code. NEXT: student codes. |
| 4 | Student submits code. | IN: `{session_id, problem_id, code}` (only these three matter; extras ignored). PROC: non-empty + ≤100_000 chars else 422. OUT: accepted submission. NEXT: execution. |
| 5 | Backend resolves problem metadata server-side. | IN: `problem_id`. PROC: `bank_loader.load_problem`; role must be canonical/transfer; language must match track. OUT: full `Problem` incl. public+hidden tests (never sent to client). NEXT: execution client. |
| 6 | Execution service receives code + tests. | IN: `{language, code, tests:[{id,input,expected_output}], timeout_seconds:5.0}` via `httpx.post(EXECUTION_SERVICE_URL/execute)`. PROC: `validate_response` contract. OUT: HTTP 200 or 422/503 mapping. NEXT: sandbox. |
| 7 | Sandbox executes the code. | IN: `solution.py` + per-test stdin. PROC: helper populates volume; student container runs each test with `--network none`, 256m/1 CPU/128 pids. OUT: per-test pass/fail + outputs. NEXT: aggregation (`FAILED`, decisive = first failure). |
| 8 | Execution result returns. | IN: sandbox results. PROC: `evaluator` aggregates; `execution_client.validate_response` re-checks counts/pointers. OUT: dict in `ExecutionResult.to_dict()` shape. NEXT: branch on status. |
| 9 | Evidence pack is created (failures only). | IN: code + `Problem` + result + `snapshot_for_evidence`. PROC: `build_pack_for_submission` (language agreement, candidate enrichment, failed-tests-only, history filter, secret scrub). OUT: `EvidencePack(observed/pending-diagnosis)`. NEXT: diagnosis. |
| 10 | Diagnosis is performed. | IN: pack. PROC: rules → LLM → fallback (§I). OUT: `{misconception_id: C3-M01, confidence: 0.70, source: fallback, explanation: "Rule C3_RANGE_BOUNDARY_EXCLUSION: …"}`. NEXT: record + intervene. |
| 11 | Misconception is identified. | `C3-M01 off-by-one-bounds` (range/len-1 shape + uniform undercount-by-one + ≥1 pass). |
| 12 | Intervention is selected. | IN: diagnosis + pack. PROC: `level_for_history` (first time ⇒ L1 NUDGE) + curated `(BOUNDARY_CHECK, loop-boundary-checks)` + decisive-test action text. OUT: `Intervention` + `student_message` (“Check whether your loop…”). NEXT: response. |
| 13 | Student receives feedback. | IN: submission response. PROC: UI renders “Your code needs improvement”, passed X/Y, hidden redaction, likely cause + “What to try”. OUT: student understands the fix. NEXT: retry. |
| 14 | Student retries. | IN: fixed code (`for x in nums`). PROC: steps 4–8 repeat. OUT: `PASSED 5/0`. NEXT: unlock transfer (no DB mastery write on this path yet — commit noop; transfer holds the verification). |
| 15 | Retry executes. | Same pipeline; all 5 tests pass. Response includes `transfer_available: true` + `transfer_problem` view. |
| 16 | Learner model records the attempt(s). | Canonical FAILED earlier already called `record_attempt(passed=False, diagnosed=C3-M01)` (mastery 0.20→0.115, counter C3-M01=1). Error statuses would record with `diagnosed=None`. NEXT: transfer attempt. |
| 17 | Transfer problem becomes available. | Gate: `canonical_pass_result is None` ⇒ 409. Otherwise transfer view served (group `ISO-C3-COUNT-DIV` never revealed). |
| 18 | Student solves related problem. | IN: cold-days code. PROC: full execution again. OUT: `PASSED`. NEXT: verification. |
| 19 | Verification compares original + transfer. | IN: `VerificationContext` (retry PASS + transfer PASS, same concept/track/group, target C3-M01). PROC: `verify_improvement` ⇒ `VERIFIED_IMPROVED / ORIGINAL_AND_TRANSFER_PASSED`. OUT: result + evidence lines. NEXT: closed loop. |
| 20 | Learner model updates (closed loop). | IN: context + catalog + curriculum. PROC: `run_closed_loop` records 2 attempts (canonical clean pass + transfer pass with `verification-target:C3-M01` ref), recomputes mastery, sweeps improvement, emits recommendations. OUT: `ClosedLoopResult(learner_updated=True, recorded=2)`. NEXT: adaptive. |
| 21 | Adaptive engine recommends next action. | IN: fresh `ConceptState/MisconceptionState` + curriculum + catalog. PROC: R1–R8 + ranking + `explain_recommendations`. OUT: e.g. practice/transfer/challenge recs with reasons. NEXT: UI shows “Continue” + recommendations; journey stage → `transfer_done`. |

> **Remember this:** *canonical FAIL teaches; canonical PASS unlocks; transfer PASS proves.*

---

## F — API map

### F.1 Complete endpoint table

**Core-backend (`cognify-core-backend v0.2.0`, base `http://localhost:8000`) — `[IMPLEMENTED]`:**

| Method | Endpoint | Purpose | Request | Response | Calls | Side Effects |
|---|---|---|---|---|---|---|
| `GET` | `/health` | Liveness. | — | `{status: ok, service: core-backend}` | none | none |
| `POST` | `/student/sessions` | Create throwaway learning session + return canonical problem. | `{language_track?: "python"}` (extra ignored; non-python → 422) | `{session_id, language_track, journey_state, problem}` | bank loader | New in-memory SQLite DB + user + journey; `localStorage` id client-side |
| `GET` | `/student/problems/{problem_id}?session_id=…` | Fetch a problem view (safe fields only). | query `session_id` | `problem_view` (no tests/answers) | bank loader | none (404 unknown session; 422 wrong journey/role/language) |
| `POST` | `/student/submissions` | Submit code; runs the whole loop branch (fail→diagnose→record→intervene; pass→unlock; transfer→verify→closed-loop). | `{session_id, problem_id, code}` (extras ignored; empty→422; >100k→422) | branch-dependent (§E steps 10/14/19: execution + diagnosis? + intervention? + recommendations + transfer? + verification? + journey_state) | execution_client → sandbox; evidence builder; diagnosis; learner_engine; adaptive; verification; closed_loop | Records attempts (FAILED/error always; verification-driven for passes); commits; stashes canonical pass; transfer-before-pass → 409; exec-down → 503; bad-response → 502 |
| `GET` | `/student/journey?session_id=…` | Read-only journey snapshot (stage, band, mastery_claim, verification, recommendations). | query `session_id` | `{session_id, language_track, canonical_problem_id, transfer_problem_id, journey_state, verification, recommendations}` | learner views + adaptive | none |
| `GET` | `/student/concepts?session_id=…` | Read-only per-concept state for all 8 concepts + adaptive next action (Step 20B). | query `session_id` | `{session_id, language_track, concepts[8] (taxonomy metadata + band/trend/counts/transfer/hints/recent-3, no mastery floats, no MID/iso), next_action}` | taxonomy + `get_concept_view/get_misconception_view` + `recommend_next_actions` over full-bank catalog | none (rollback before return; repeated GETs identical) |
| `GET` | `/student/history?session_id=…&limit=…` | Read-only student-safe attempt history (Step 20B). | query `session_id`, `limit` default 20, clamped to 50, `<1` → 422 | `{session_id, total, limit, items[] (order/created_at/problem+concept titles/outcome/feedback/verified)}` | existing append-only `attempt` events + bank/taxonomy titles | none (rollback before return) |
| `GET` | `/student/problems?session_id=…` | Read-only safe problem catalog from the bank loader (Step 20B). | query `session_id` | `{session_id, language_track, total, problems[] (id/title/language/concept+difficulty/role/redacted description)}` | `load_all_problems` (discovers future additions) | none (no tests/MIDs/iso/solutions serialized) |

**AI service (`cognify-ai-service v0.2.0`, base `http://localhost:8001`) — `[IMPLEMENTED]`:**

| Method | Endpoint | Purpose | Request | Response | Calls | Side Effects |
|---|---|---|---|---|---|---|
| `GET` | `/health` | Liveness. | — | `{status: ok, service: ai-service}` | none | none |
| `POST` | `/diagnose` | Diagnose one EvidencePack (rules → LLM → fallback). | `{evidence_pack: {...}}` (`extra=forbid`; bad pack → 422) | `DiagnosisResult` (always 200 on valid pack: concept/MID/confidence/explanation/refs/source) | rules/LLM/fallback | none (stateless; never writes learner state) |

**Execution service (`cognify-execution-service v0.2.0`, base `http://localhost:8002`) — `[IMPLEMENTED]`:**

| Method | Endpoint | Purpose | Request | Response | Calls | Side Effects |
|---|---|---|---|---|---|---|
| `GET` | `/health` | Liveness. | — | `{status: ok, service: execution-service}` | none | none |
| `GET` | `/languages` | Advertised runtimes. | — | `{languages: [python, java]}` | none | none |
| `POST` | `/execute` | Run code vs tests in Docker sandbox. | `{language, code, tests[1..50], timeout_seconds ∈ [1,30]}` (empty code / >100k / bad language → 422) | `ExecutionResult` (status, per-test results, passed/failed counts, decisive pointers) | runner → Docker sandbox | Containers + temp volume created then removed; Docker-down → 503 |

**`[PLANNED / NOT IMPLEMENTED]` endpoints:** `DELETE`/reset, auth/login, instructor dashboard,
problem CRUD — none exist in code. (Per-concept progress, attempt-history list, and the problem
catalog shipped as read-only Step 20B endpoints — see the three `GET` rows above.)

### F.2 Request lifecycle: `POST /student/submissions` (the whole viva in one diagram)

```text
Browser (practice page: session_id, problem_id, code)
 ↓  POST /student/submissions (JSON; unknown fields dropped)
student.py: validate session (404) → validate code non-empty/≤100k (422)
 ↓  _resolve_problem: bank load (404) → role check (422) → language-track check (422)
execution client: build_payload → httpx.post(EXECUTION_SERVICE_URL/execute)
 ↓  execution-service: validate → evaluator → runners → sandbox → aggregate
execution result dict (or Unavailable→503 / BadResponse→502, fail-closed)
 ↓  BRANCH:
   canonical FAILED → build EvidencePack → diagnose → record_attempt(passed=False)
                      → intervention + adaptive recs → commit → respond (transfer locked)
   canonical PASSED → stash pass (no mastery write) → respond (transfer unlocked)
   transfer submit  → require prior canonical pass (else 409) → execute → verify
                      → run_closed_loop (record 2/2/1/0) → commit → respond
   error status     → record_attempt(passed=False, diagnosed=None) → safe message
 ↓  Browser renders ResultPanel (passed X/Y, hidden redaction, cause, what-to-try, continue)
```

### F.3 Validation / errors / status codes / security restrictions

- **Validation:** pydantic shapes (`extra=ignore` on student I/O so spoof fields are dropped;
  `extra=forbid` on AI/execution I/O so malformed shapes 422); code empty/oversize; timeout/test-count
  bounds; taxonomy belonging; `passed`⇔`PASSED` agreement; transfer gating (409).
- **Error handling:** `404` unknown session/problem; `422` validation/track/role/language/payload;
  `409` transfer-before-pass; `502` execution bad-response; `503` execution/sandbox unavailable.
  Error bodies are scrubbed (tests assert no `Traceback/sqlalchemy/DATABASE_URL/sk-` leakage).
- **Status codes:** HTTP codes above are transport-level; grading outcomes are the 5
  `ExecutionStatus` values inside 200 bodies (§G). Never confuse the two in viva.
- **Security restrictions:** hidden tests never serialized (`problem_view` allowlist + `to_student_view`
  redaction + 2000-char truncation); isomorphic groups never revealed; client concept/language/
  mastery/diagnosis/verification values ignored (spoof test proves `C8/java/mastery:1.0` still yields
  `FAILED + C3-M01`); CORS allowlist (`STUDENT_CORS_ORIGINS`, default localhost:3000; evil-origin test).
- **Hidden-test handling:** decisive hidden failures surface as counts + generic guidance only
  (“This test's details stay hidden”); `expected_output/actual_output` top-level pointers are `None`
  for hidden decisive tests; tests assert `"expected_output": "<hidden>"` never leaks.
- **Spoofing protection:** `_resolve_problem` + request-model allowlists mean the only client-controlled
  grading input is the code text itself. `Inferred from implementation.`

> **Remember this:** *“Three strings in, truth out — everything that matters is resolved server-side.”*

---

## G — Execution pipeline

### G.1 The exact path (code locations)

```text
student._execute(problem, code)                       [core-backend/app/student.py]
 → execution_client.execute_problem(problem, code, 5.0) [core-backend/app/execution_client.py]
    → httpx.post(http://execution-service:8002/execute)  (timeout = max(10, 5*(n+1)+10))
      → main.execute → default_runner_factory          [execution-service/app/main.py]
      → evaluator.evaluate(language, code, cases, timeout) [app/evaluator.py]
          → runner.compile(code, timeout)               [runners.py / java_runner.py]
             (non-None ⇒ COMPILE_ERROR result, no tests run)
          → per test: runner.run_single(code, stdin, timeout)
              → python_runner: sandbox.run({solution.py}, [python /workspace/solution.py])
              → java_runner:   sandbox.run({Main.java}, [sh -c "javac … && java …"])
                → DockerSandboxRunner.run()             [app/sandbox.py]
                   ① docker_available() else SandboxUnavailableError (fail-closed)
                   ② validate files/command; names cognify-exec-vol-*/cognify-exec-*/cognify-workspace-*
                   ③ _populate_volume via HELPER container (python:3.11-slim, --network none)
                   ④ docker run STUDENT container (limits below) with stdin piped
                   ⑤ timeout → kill container → TIMEOUT result; finally volume rm
          → normalize outputs → compare → aggregate status + decisive pointers
      → ExecutionResult JSON (200) / 422 / 503
    → validate_response (deep contract incl. counts-vs-per-test agreement, decisive mirroring)
 → student branches (§E)
```

### G.2 Limits (all from code — quote these numbers)

| Concern | Value | Location |
|---|---|---|
| Code size | `≤ 100_000` chars (both core + execution validation) | `student.MAX_CODE_CHARS`, `models.MAX_CODE_CHARS` |
| Tests per request | 1–50 | `models.MAX_TESTS_PER_REQUEST` |
| Timeout per test/compile | 1.0–30.0 s, default 5.0 s (student slice uses 5.0) | `models.*TIMEOUT*`, `student.TIMEOUT_SECONDS` |
| HTTP timeout (core→exec) | `max(10, timeout*(n_tests+1)+10)` s | `execution_client.execute_problem` |
| Memory | `256m` (+`--memory-swap 256m`) | `sandbox.DEFAULT_MEMORY` |
| CPU | `1.0` | `sandbox.DEFAULT_CPUS` |
| PIDs | `128` | `sandbox.DEFAULT_PIDS_LIMIT` |
| Network | `none` (helper hardcoded; student default `none`) | `sandbox.build_command` |
| Filenames | relative only, no `..`/absolute | `sandbox` filename guard |
| View truncation | 2000 chars per text field | `student.MAX_VIEW_TEXT_CHARS` |

### G.3 Why the helper container exists

The execution service itself runs **inside Docker** while the daemon lives outside that container,
so a host bind-mount would not resolve. Instead a throwaway **helper container** (same limits,
`--network none`) receives the file payload on stdin and writes it into a fresh **Docker-managed
named volume** (`cognify-exec-vol-<hex>`); the student container then mounts that volume at
`/workspace`. The helper only writes files — it never executes student code
(`sandbox.py` helper script is a fixed `path.write_text` loop).

### G.4 Why core-backend never executes student code directly

- **Blast radius:** untrusted code must never share a process/host with learner state, sessions,
  or secrets. `student._default_runner_factory` raises `RuntimeError("Local execution is disabled…")`
  instead of creating any local runner, and tests assert the source never references local runner
  classes and that HTTP failure never falls back to local execution (`PWNED` probe).
- **Contract:** execution is a network boundary with a validated response schema, so the orchestrator
  can fail closed (503/502) with scrubbed messages.

### G.5 What happens when Docker is unavailable

`sandbox.run` raises `SandboxUnavailableError("Docker is unavailable; refusing to execute student
code on the host.")` → `main.execute` maps to **HTTP 503** → `execution_client` raises
`ExecutionServiceUnavailable` → `student._execute` maps to **HTTP 503** → frontend shows
“Code execution is temporarily unavailable…”. Helper timeout/failure maps the same way. There is
**no host fallback, no queue, no retry** in code. `[IMPLEMENTED]` fail-closed; retries/queue are
`[PLANNED / NOT IMPLEMENTED]`.

### G.6 Python vs Java

- **Python `[IMPLEMENTED]`:** `python:3.11-slim`, `solution.py`, `python /workspace/solution.py`,
  no compile step ⇒ `SyntaxError` surfaces as `RUNTIME_ERROR` (not `COMPILE_ERROR`).
- **Java `[PARTIALLY IMPLEMENTED]`:** `eclipse-temurin:17-jdk`, `Main.java` must define
  `public class Main`; `compile()` runs `javac` once and short-circuits failures correctly, BUT
  `run_single()` re-runs `javac … && java …` **per test** (wasteful double compilation; also uses
  `sh -c`). Works, inefficient. No Java track in UI/bank (`GET /languages` advertises it; nothing
  else consumes it). `Inferred from implementation.`
- Output comparison is whitespace-tolerant (`\r\n→\n`, rstrip each line, strip whole) but raw
  `stdout` is preserved as `actual_output`. Status precedence: any `timed_out` ⇒ `TIMEOUT`;
  elif any `exit_code != 0` ⇒ `RUNTIME_ERROR`; elif any mismatch ⇒ `FAILED`; else `PASSED`.
  Only `PASSED` counts as passing everywhere downstream.

> **Remember this:** *“Student code never touches our host — only the Docker CLI does, with no
> network, capped memory/CPU/PIDs, and a guaranteed cleanup.”* Do NOT claim gVisor, Firecracker,
> Kubernetes, or host-interpreter execution — none exist in code.

---

## H — Evidence pack

### SIMPLE EXPLANATION

Before Cognify “thinks”, it writes down **what it saw**: the code, which test broke, what was
expected, what actually came out, and what this student struggled with before. That note is the
EvidencePack. Every later claim must point at lines in that note.

### TECHNICAL EXPLANATION

`EvidencePack` (`packages/evidence/models.py`, schema `1.0`) is the sole input to diagnosis.
Built by `build_evidence_pack(code, problem, execution_result, learner_snapshot)`:
language agreement enforced (problem == execution == learner, else `ValueError`); candidates
enriched from taxonomy in problem order; execution copied raw but only failed tests kept, in
order; concept history copied verbatim (never computed); misconception history/flags filtered to
pack candidates and sorted; recent events trailing-sliced (≤10), same-concept-only, secret-scrubbed;
`evidence_kind="observed"`, `confirmed=None`, `inference_status="pending-diagnosis"`.

### What evidence is collected?

| Evidence | Source | Notes |
|---|---|---|
| Submitted `code` (verbatim, ≤100k) | student | Never modified; AST rules read it read-only. |
| `failed_tests[]` (failed only, in order) + decisive `failed_test_id` | sandbox | Each: id, input, expected/actual, stdout/stderr, exit_code, timed_out, time_ms. |
| `expected_output` / `actual_output` top-level pointers | evaluator | Must mirror the FIRST failed test (validated both directions). |
| `execution_status` + `passed/failed_count` + `stdout/stderr` | evaluator | Counts must agree with per-test booleans; `failed==0` ⇒ pointers `None` + all passed. |
| `misconception_candidates[]` (≥1, unique, same-concept) | problem + taxonomy | “Suspects”, never conclusions; enriched with name + typical_signal. |
| `concept_history` (stored mastery, attempts, band, trend, hints, transfers) | learner snapshot | Copied verbatim — builder never computes mastery. |
| `misconception_history[]` + `recurring_flags[]` | learner snapshot | Candidate-only; supports fallback scoring + intervention levels. |
| `recent_events[]` (≤10, same-concept) | learner events | Sanitized via `sanitize_metadata` (drops password/secret/token/api_key/… recursively). |

### Why is evidence important? Why shouldn’t the LLM simply guess?

- **Grounding:** validator + gate force every diagnosis to cite observable refs
  (`failed_test:<id>`, `expected_output`, `actual_output`, `code`, …). A beautiful explanation
  with no citation is rejected and replaced by fallback.
- **Memory:** history fields let fallback/interventions/adaptive distinguish “first slip” (L1 nudge)
  from “third recurrence” (L4 reteach) instead of treating every failure identically.
- **Auditability:** `explain_mastery` + event log can replay exactly which evidence moved mastery
  and why — a reviewer can check the receipts.
- **Hallucination reduction:** the candidate list + concept equality + ref resolvabilityChecks make
  inventing a misconception a validation error, not a diagnosis. Tests prove hallucinated MIDs,
  wrong-concept MIDs, and ungrounded refs all fall back to deterministic output.

> **Remember this:** *“No evidence, no diagnosis. The pack is the only thing the brain may read.”*

---

## I — AI diagnosis

### Architecture (memorize the order)

```text
EvidencePack
 → try_rule_diagnosis  (2 deterministic C3 rules; self-checked by validator+gate)
     HIT (conf 0.70, "Rule <ID>:" prefix, source="fallback") → DONE (LLM never called)
     MISS (None)
 → LLM client (None ⇒ skip; complete() raises ⇒ fallback)
     → _parse_llm_json (markdown-fence tolerant; empty/non-JSON ⇒ fallback)
 → validate_llm_diagnosis (schema+taxonomy+grounding; raises ⇒ fallback)
 → confidence_grounding_gate (conf ≥ 0.50 AND failure-grounded; else fallback)
 → source="llm"  (only here)
 → ANY failure ⇒ fallback_diagnose (deterministic classifier, source="fallback")
 → build_intervention (level L1–L4 + curated type/skill)
```

So there are exactly **two** reported sources (`DiagnosisSource = llm | fallback`): rule hits
are deterministic and therefore reported as `fallback`, distinguishable by the `Rule <RULE_ID>:`
explanation prefix and the higher 0.70 confidence (generic fallback caps at 0.55).

### I.1 DETERMINISTIC RULES `[IMPLEMENTED]` (C3 only)

Common guards for both rules: concept must be `C3`, language `python`, target MID in candidates,
status `FAILED` with ≥1 failed test. Both run through `validate_llm_diagnosis` + gate internally
(`_checked`) before firing, and never match on `problem_id`.

| Rule | Concept | Trigger (ALL must hold) | Evidence Required | Misconception | Confidence | Intervention |
|---|---|---|---|---|---|---|
| `C3_RANGE_BOUNDARY_EXCLUSION` | C3 loops | AST finds `range(..., len(X)-1)` (terminal-index exclusion) AND **every** failed test has `actual == expected-1` (expected ≥ 1) AND `passed_count ≥ 1` | code shape + uniform undercount-by-one across all failures + at least one passing test | `C3-M01 off-by-one-bounds` | 0.70 | `BOUNDARY_CHECK / loop-boundary-checks` |
| `C3_RANGE_EXCLUSIVITY` | C3 loops | AST finds `range(<int start>, <bare-name stop>)` e.g. `range(1, n)` (single-arg `range(n)` does NOT match) AND **every** failed test has `actual == expected-n` where `n` = the single-int test input ≥ 1 | code shape + every failure drops exactly its terminal value | `C3-M05 python-range-exclusivity` | 0.70 | `TRACE_LOOP / range-stop-semantics` |

Refs emitted: `["failed_test:<decisive>", "expected_output", "actual_output", "code"]`.
Example explanation: `“Rule C3_RANGE_BOUNDARY_EXCLUSION: the code iterates range(len(nums) - 1),
excluding the terminal index, and every failed test undercounts by exactly one (decisive P2:
expected 3, got 2). This matches C3-M01 …”`.
Abstention cases (tested): example pack, code-without-output, output-without-code, missing
candidate, non-uniform failures, `passed_count==0` (R1), `PASSED`/`RUNTIME_ERROR`/unparseable
code — all return `None`.

### I.2 LLM REASONING `[IMPLEMENTED]` but dormant by default

- Prompt (`prompt.py`): fixed system template (7 rules: candidate-only, concept equality,
  confidence ∈ [0,1], explanation 10–500 chars, refs from an allowlist, JSON-only, “do NOT update
  any database / calculate mastery / generate hints / make roadmap decisions”) + user message with
  pack JSON (`sort_keys=True` ⇒ deterministic) + candidate list + decisive test. Same pack ⇒ same prompt.
- Client (`llm_client.py`): OpenAI-compatible `POST {base}/chat/completions` with
  `temperature: 0.0` + `response_format: {json_object}`; 401/403/429 ⇒ `LLMUnavailableError` ⇒ fallback.
  Config (`config.py`): providers `""/openai/mock`; default model `gpt-4o-mini`, base
  `https://api.openai.com/v1`, timeout `30.0 ∈ [1,120]`; `openai` requires `LLM_API_KEY`.
- Default `.env` has **`LLM_PROVIDER=` (empty)** ⇒ `enabled == False` ⇒ deterministic mode
  (Step-15 rules, then safe fallback). Set `LLM_PROVIDER=openai` + key to enable model diagnosis.
- The LLM receives **only the rendered prompt** — no DB access, no tools, no other student data.

### I.3 When each is used

1. Rules first (cheap, exact, no network). A hit bypasses the LLM entirely (proven by
   `client.calls == []` test assertion).
2. LLM second (only if rules abstain AND a client is configured). Must survive validator + gate.
3. Fallback always (any miss/failure/unavailability). Never `None`, never an error to the caller.

### I.4 Candidate misconceptions, confidence, abstention, validation, fallback, source labels

- **Candidates:** from the problem’s `misconception_ids`, enriched via taxonomy (never confirmed).
- **Confidence:** rule 0.70; LLM whatever passes ≥ 0.50 gate; fallback `min(score, 0.55)` (0.40 if no failure).
- **Abstention:** rules abstain with `None` unless ALL predicates hold (§I.1 list).
- **Validation:** `validator.py` 7-check sequence (§D.2); extra keys (e.g. `mastery`, `hint`) are errors.
- **Fallback:** `0.30 + 0.20·recurring + min(0.05·count, 0.15)`; deterministic tie-breaks; refs
  `[failed_test:<id>, expected_output, actual_output]` (or `[execution_status, code]` if no failure).
- **Source labels:** `llm` = grounded LLM diagnosis passed validator+gate; `fallback` = everything
  deterministic (rule hits carry `Rule <ID>:` prefix + 0.70; generic fallback carries `Fallback:` prefix).

### What happens when the AI cannot confidently diagnose?

It returns a **grounded deterministic fallback**, still HTTP 200 with a full `DiagnosisResult`:
highest history-informed candidate, capped confidence, `Fallback: …` explanation, failure-citing
refs. Only a malformed `EvidencePack` itself yields 422. There is no “I don’t know” response shape —
uncertainty is expressed as low confidence + `confidence_label: uncertain` downstream
(`student._confidence_label`: ≥0.70 likely, ≥0.50 possible, else uncertain).

> **Remember this:** *“Rules before models, validation before trust, fallback before silence.”*

---

## J — Misconception taxonomy

`[IMPLEMENTED]` — `packages/taxonomy/` is the single source of truth; every layer validates
against it (DB CHECKs, repositories, validator, interventions, evidence builder, adaptive).

### Concepts C1–C8 (from `concepts.py`)

| ID | Title | Topics | Prerequisites |
|---|---|---|---|
| C1 | Variables, Types, Operators, I/O | variables-and-assignment, primitive-types, operators-and-precedence, type-conversion, console-io | — |
| C2 | Conditionals & Boolean Logic | if-else-branching, boolean-operators, short-circuit-evaluation, nested-conditionals, switch-and-chained-comparison | C1 |
| C3 | Loops & Iteration Control | for-loops, while-loops, loop-bounds-and-termination, break-continue, nested-loops | C1, C2 |
| C4 | Functions / Methods, Parameters, Scope & Return | function-definition-and-calls, parameters-and-arguments, return-values, scope-and-shadowing, call-semantics | C1, C2, C3 |
| C5 | Lists / Arrays & Strings | indexing, slicing-and-substrings, aliasing-vs-copying, string-immutability, length-vs-last-index | C1, C3, C4 |
| C6 | Dictionaries / Maps, Sets & Nested Structures | dict-map-basics, sets-and-membership, missing-key-handling, mutation-during-iteration, nested-structure-access | C1, C3, C5 |
| C7 | OOP: Classes, Objects, Encapsulation, Inheritance | class-vs-instance, constructors, encapsulation-and-access-control, inheritance-and-super, static-vs-instance | C1, C4, C5 |
| C8 | Recursion, Exceptions & Algorithmic Complexity Basics | base-and-progress-cases, raising-and-handling-exceptions, recursion-vs-iteration, big-o-basics | C2, C3, C4, C7 |

### Misconceptions per concept (48 total; IDs `C*-M**`; from `errors.py`)

Pattern per concept: 4 shared (`python`+`java`) + 1 python-only + 1 java-only.
Language scope: `("python","java")` = shared, `("python",)` / `("java",)` = specific.

- **C1:** `C1-M01` assignment-vs-equality · `C1-M02` type-coercion-and-division ·
  `C1-M03` unconverted-input · `C1-M04` operator-precedence ·
  `C1-M05` python-dynamic-typing-and-none (py) · `C1-M06` java-static-types-scanner-and-init (java).
- **C2:** `C2-M01` boolean-operator-confusion (`if x == 1 or 2:`) · `C2-M02` demorgan-negation ·
  `C2-M03` branch-coverage-and-nesting · `C2-M04` truthiness-vs-explicit-compare ·
  `C2-M05` python-chained-comparison (py) · `C2-M06` java-switch-fallthrough-and-string-compare (java).
- **C3:** `C3-M01` off-by-one-bounds · `C3-M02` non-termination · `C3-M03` break-continue-semantics ·
  `C3-M04` accumulator-and-loop-var-reuse · `C3-M05` python-range-exclusivity (py) ·
  `C3-M06` java-for-header-and-iterator (java).
- **C4:** `C4-M01` value-vs-reference-call-semantics · `C4-M02` scope-and-shadowing ·
  `C4-M03` missing-or-ignored-return · `C4-M04` arity-and-argument-order ·
  `C4-M05` python-mutable-default-argument (`def f(xs=[])`) (py) ·
  `C4-M06` java-signatures-overloading-and-void (java).
- **C5:** `C5-M01` index-vs-length (`xs[len(xs)]`) · `C5-M02` aliasing-vs-copying ·
  `C5-M03` string-immutability · `C5-M04` search-and-split-edge-cases ·
  `C5-M05` python-slicing-and-negative-index (py) · `C5-M06` java-array-vs-arraylist-and-string-equals (java).
- **C6:** `C6-M01` missing-key-handling · `C6-M02` mutation-during-iteration ·
  `C6-M03` hashability-and-equality-contract · `C6-M04` unsafe-nested-access ·
  `C6-M05` python-get-setdefault-and-set-semantics (py) · `C6-M06` java-map-impl-ordering-and-optional-get (java).
- **C7:** `C7-M01` class-vs-instance · `C7-M02` constructor-misuse · `C7-M03` encapsulation-violation ·
  `C7-M04` inheritance-and-super · `C7-M05` python-self-and-dunder (py) ·
  `C7-M06` java-static-vs-instance-and-modifiers (java).
- **C8:** `C8-M01` missing-base-or-progress (`RecursionError/StackOverflowError`) ·
  `C8-M02` exception-swallowing (bare `except: pass`) · `C8-M03` recursion-vs-iteration-and-depth ·
  `C8-M04` big-o-misjudgment · `C8-M05` python-bare-except-and-recursion-limit (py) ·
  `C8-M06` java-checked-exceptions-and-throws (java).
- **Cross-cutting (5):** `X-SYNTAX` syntax-error · `X-COMPILE` compilation-error ·
  `X-RUNTIME` runtime-error · `X-TIMEOUT` timeout · `X-WRONG-OUTPUT` wrong-output.

### How a misconception ID travels (trace `C3-M01` through the system)

```text
Problem (misconception_ids: [C3-M01, C3-M04])
 ↓  candidates enrich the EvidencePack (suspects, not verdicts)
Diagnosis (rules/LLM/fallback pick exactly one: C3-M01, conf 0.70, refs cite P2 + code)
 ↓  record_attempt: MisconceptionCounter(C3-M01) +1, last_seen=now, reactivate if needed
Recurring detection (recent_occurrence_count + isomorphic_variant_count → check_recurring)
 ↓  flag C3-M01 recurring (reason “2 in last 5” / “3 historical” / “2 variants”)
Intervention (level_for_history → L2/L3/L4; C3-M01 → BOUNDARY_CHECK/loop-boundary-checks)
 ↓  student retries + transfer; verification names C3-M01 as target_misconception_id
Adaptive (MisconceptionState(C3-M01, recurring) → REVIEW_CONCEPT/REMEDIAL +15 priority,
         suppresses TRANSFER/CHALLENGE until cleared)
 ↓  3 clean relevant passes with no recurrence → has_improved → deactivate + clear flag
```

> **Remember this:** *“The ID is born in the bank, chosen by evidence, counted by the learner
> model, taught by the intervention, tested by transfer, and cleared only by sustained success.”*

---

## K — Learner model

### SIMPLE EXPLANATION

The learner model is Cognify’s **memory of the student**: how well they know each concept, what
mistakes they keep making, whether they depend on hints, whether fixes transfer, and the full
history behind every number.

### TECHNICAL EXPLANATION

The learner model = SQLAlchemy tables (`models.py`) + validation (`repositories.py`) + read/write
logic (`learner_engine.py`) + math (`packages/mastery/`). Writes go only through
`learner_engine.record_attempt`; reads go through `get_concept_view / get_misconception_view /
explain_mastery / snapshot_for_evidence`. Connection config lives in `db.py`. AI code is banned
from importing `db.py`.

### What is stored for a concept? (per `(journey, concept)`)

| Field family | Columns / derived | Meaning |
|---|---|---|
| Identity | `user_id, journey_id, concept_id, language_track` | Track isolation: python/java never mix (mismatch ⇒ `ValueError`, “tracks must not cross”). |
| Mastery | `mastery` Float ∈ [0,1] (fresh → `0.20`), `current_band` (novice/emerging/proficient/mastered/unassessed), `trend` (unknown/stable/improving/declining) | The number, its band, its direction. `unassessed/unknown` are the pre-first-attempt defaults. |
| Attempts | `attempt_count, successful_attempts` (+ derived `fail_count`, `pass_count`) | Totals; recent-5 window derived from events for momentum/trend. |
| Hint dependence | `hint_count` (+ derived `hint_dependence` = hints/attempts, 0 when none) | Independence matters: hints damp gains and can suppress challenge/transfer. |
| Transfer | `transfer_attempts, transfer_successes` (+ derived failures/rate, canonical-vs-transfer breakdown) | Whether fixes survive new contexts. |
| Recent history | last-5 `[{problem_id, passed, hint_used, is_transfer}]` oldest→newest + `last_attempted_at` | Powers momentum (`recent_pass_rate`), trend (`compute_trend`), and UI. |
| Misconceptions | `MisconceptionCounter(concept,mid): occurrence_count, last_seen_at, active` + `RecurringFlag(mid): is_recurring, reason, detected_at` | Per-misconception counts, liveness, recurrence verdicts. |
| Supporting refs | `supporting_problem_ids[]` (distinct, sorted), `supporting_groups[]` (distinct iso groups, sorted), `distinct_variant_count` | Which problems/groups evidenced the weakness (R3 needs ≥2 variants). |
| Evidence | `LearnerEvent` rows: `attempt` (passed/status/hint/transfer/refs/attempt_number), `diagnosis` (MID+confidence), `mastery_transition` (prev/new/delta/reason/bands/trend/flags), `recurring_detected/cleared` | Append-only audit trail; `explain_mastery` correlates transitions to attempts for the narrative. |
| Transition events | same event log | `explain_mastery` returns `{concept_view, transitions[], narrative}` for review. |

### Who is allowed to update it?

ONLY `services/core-backend/app/learner_engine.py` (via `repositories.py` into a caller-committed
session). Concretely: `student.py` (FAILED/error submissions) and `closed_loop.run_closed_loop`
(verification-driven records). `repositories` flushes but never commits; `db.py` is never imported
by ai-service (module docstring ban, enforced by tests that grep for `learner_engine/sqlalchemy` in
AI code). Adaptive/verification/evidence packages are pure and stateless.

### Why must the LLM never directly modify learner state?

1. **Safety:** model output is probabilistic; state must be reproducible. A hallucinated MID or
   invented mastery would corrupt every downstream decision (recurring flags, adaptive ranking).
2. **Auditability:** all mutations pass validation + belonging checks + event logging in one place.
3. **Separation of powers:** the reasoner proposes; the engine disposes after validation, gating,
   execution evidence, and transfer evidence. Reviewers should hear this sentence verbatim.

> **Remember this:** *“The LLM has no hands — only the learner engine can write, and only through
> record_attempt.”*

---

## L — Mastery calculation

`[IMPLEMENTED]` — sole owner `packages/mastery/formula.py` (pure; no LLM/clock/randomness/I-O/DB).
Applied by `learner_engine.record_attempt` with `prior_rate` = trailing-5 pass rate (0.5 when no
history ⇒ zero momentum on the first attempt). Result clamped to [0,1] and rounded to 4 decimals.

### Actual constants (quote these)

```python
INITIAL_MASTERY = 0.20
PASS_BASE_GAIN = 0.12
TRANSFER_BONUS = 0.04
HINT_DAMPING = 0.5
MOMENTUM_SCALE = 0.04
FAIL_BASE_PENALTY = 0.05
FAIL_SEVERITY_SCALE = 0.07
HINT_FAIL_PENALTY = 0.02
TRANSFER_FAIL_PENALTY = 0.01
SEVERITY_BY_STATUS = {"PASSED": 0.0, "FAILED": 0.5, "COMPILE_ERROR": 0.75,
                      "RUNTIME_ERROR": 0.75, "TIMEOUT": 1.0}
```

### Formula (verbatim from `formula.py` docstring)

```text
On PASS (execution_status == "PASSED"):
  base_gain   = 0.12
  if hint_used:   base_gain *= 0.5
  if is_transfer: base_gain += 0.04
  momentum    = (recent_pass_rate - 0.5) * 0.04
  delta       = base_gain + momentum              # in [0.04, 0.18]

On FAIL (any non-PASSED terminal status):
  severity      = severity_for_status(execution_status)   # 0.5..1.0
  base_penalty  = -(0.05 + 0.07 * severity)
                  # FAILED -> -0.085, COMPILE/RUNTIME -> -0.1025, TIMEOUT -> -0.12
  if hint_used:   base_penalty -= 0.02
  if is_transfer: base_penalty -= 0.01
  momentum      = (recent_pass_rate - 0.5) * 0.04
  delta         = base_penalty + momentum           # in [-0.17, -0.065]

new = clamp(round(previous + delta, 4))
```

Plus: `passed`⇔`PASSED` agreement enforced both directions (mismatch ⇒ `ValueError`);
reason strings encode the branch, e.g. `pass+independent+canonical+cold-start (recent 0.50,
momentum +0.000, base +0.120)` or `fail/failed+independent+canonical+cold-streak (severity 0.50, …)`.

### Bands, trend, clamping, rounding

- **Bands** (`mastery_band`): `< 0.40 → novice`; `0.40–0.59 → emerging`; `0.60–0.79 → proficient`;
  `≥ 0.80 → mastered`. (Boundary tests: 0.39 novice / 0.40 emerging / 0.59 emerging / 0.60
  proficient / 0.79 proficient / 0.80 mastered.)
- **Trend** (`compute_trend` over oldest→newest outcomes): `[] → unknown`; last ≤3 all-True (≥2) →
  `improving`; all-False (≥2) → `declining`; else `stable` (incl. single attempts).
- **Clamping/rounding:** `new = round(clamp(previous + delta), 4)`; floors at 0.0 (20 timeouts → 0.0),
  caps at 1.0 (20 passes → mastered, no overflow).
- **Initial mastery:** fresh concept state → `0.20 / novice / unknown` (raw DB default is `0.0`;
  `ensure_concept_state` normalizes on first use).

### Numerical example (actual constants; neutral momentum `recent = 0.50 ⇒ momentum 0.000`)

```text
Start:                          mastery 0.2000 (novice)
 ↓ FAIL FAILED, no hint, canonical:  delta = -(0.05 + 0.07*0.5) + 0 = -0.085
After fail:                     mastery 0.1150 (novice)
 ↓ PASS with hint, canonical:    base = 0.12*0.5 = 0.06; delta = +0.060
After hinted pass:              mastery 0.1750 (novice)
 ↓ PASS independent, TRANSFER:   base = 0.12+0.04 = 0.16; delta = +0.160
After transfer pass:            mastery 0.3350 (novice)
 ↓ TIMEOUT, no hint, canonical:  delta = -(0.05 + 0.07*1.0) = -0.120
After timeout:                  mastery 0.2150 (novice)
```

Reference points from tests: `0.20 → pass ⇒ 0.32 (Δ+0.12)`; `0.20 → hinted pass ⇒ 0.26`;
`0.20 → transfer pass ⇒ 0.36`; `0.50 → FAILED ⇒ 0.415 (Δ−0.085)`; `0.50 → TIMEOUT ⇒ 0.38 (Δ−0.12)`;
hot streak (`recent 1.0`) outgains cold (`recent 0.0`) by `0.04`. A single pass never masters
(`0.20 → 0.32`, still novice) — mastery needs sustained evidence.

> **Remember this:** *“Passes build slowly (+0.12), timeouts destroy quickly (−0.12), hints halve
> gains, transfer adds +0.04, and momentum rewards consistency.”*

---

## M — Recurring misconception detection

`[IMPLEMENTED]` — predicates in `packages/mastery/weakness.py` (pure); bookkeeping in
`learner_engine.record_attempt` (counters → flags → events).

### Thresholds (exact)

```python
RECENT_WINDOW = 5
RECENT_THRESHOLD = 2
HISTORICAL_THRESHOLD = 3
VARIANT_THRESHOLD = 2
IMPROVEMENT_WINDOW = 3
```

### Every rule

| Rule | What it checks | Evidence required | Reason string |
|---|---|---|---|
| **R1 recent** | Same MID ≥ **2** times in the **last 5** attempts. | `recent_occurrence_count(histories + [current], mid, 5) ≥ 2`. Current attempt appended explicitly (histories exclude it first). | `recurring: {recent} occurrence(s) in the last 5 attempts (>= 2)` |
| **R2 historical** | Same MID ≥ **3** times ever. | `occurrence_count` (the counter, incl. current increment) `≥ 3`. | `recurring: {total} historical occurrence(s) (>= 3)` |
| **R3 variants** | Same MID across ≥ **2 isomorphic variants**, i.e. max distinct `problem_id`s within any ONE `isomorphic_group_id` ≥ 2. Bare distinct problems are NOT enough. | `isomorphic_variant_count([(problem, group), …] + [(current_problem, current_group)]) ≥ 2`. Same-group pair ⇒ 2; two different groups ⇒ 1 (not recurring). | `recurring: seen across {v} isomorphic problem variant(s) (>= 2)` |

Evaluation order R1 → R2 → R3; else `not recurring: recent {r}<2, historical {t}<3, variants {v}<2`.

### Why recurrence matters

One failure = a slip. Recurrence = a **stable wrong mental model** that needs reteaching, not a
nudge: it escalates interventions (L3/L4), boosts adaptive priority (+15), and suppresses
transfer/challenge until cleared. The variant rule (R3) is the strongest signal — the student makes
the same mistake in *different surface stories*, so it cannot be dismissed as memorizing one problem.

### Isomorphic groups + distinct variants

Each problem carries `isomorphic_group_id` (e.g. `ISO-C3-COUNT-DIV` shared by canonical + transfer).
`isomorphic_variant_count` groups occurrence `(problem_id, group_id)` pairs by group and returns the
max distinct-problem count inside any single group (skips empty/None). So `[(P1,G),(P1,G)]` ⇒ 1,
`[(P1,G),(P2,G)]` ⇒ 2, `[(P1,G1),(P2,G2)]` ⇒ 1.

### When a misconception becomes recurring / improved / cleared

- **Becomes recurring:** `check_recurring(...)` true ⇒ `set_recurring_flag(True, reason)` + append
  `recurring_detected` event — but ONLY on the `False → True` transition (no spam).
- **Considered improved:** `has_improved(pairs, mid)`: the trailing `IMPROVEMENT_WINDOW` (3) relevant
  attempts (prior + current) are ALL passes AND none re-contains the MID.
- **Cleared:** the engine sweeps every active same-concept counter after each attempt; improved ones
  are deactivated + flag set `False` with reason `improved: no recurrence in last 3 relevant attempts
  (all passed)` + `recurring_cleared` event; their IDs land in `improved_ids`. In the student slice,
  3 clean passes resolve (tested).

### Realistic example

```text
Attempt 1: PY-C3-COUNT-DIV FAIL, diagnosed C3-M01 → counter=1, recent=1, variants=1 → not recurring → L1.
Attempt 2: PY-C3-COUNT-DIV FAIL, diagnosed C3-M01 → counter=2, recent=2 → R1 fires →
           flag TRUE (“2 occurrence(s) in the last 5”), L3 SCAFFOLD, adaptive +15.
Attempt 3: retry PASS (clean, no MID) → counter stays; not yet improved (need 3 clean).
Attempt 4: PY-C3-COUNT-DIV-TRANSFER PASS (clean) → variants still 1 group… wait — both in
           ISO-C3-COUNT-DIV, but R3 needs the MID on ≥2 variants; clean passes don’t add
           occurrences, so R3 stays 1 while R1/R2 already hold the flag. Correct per code.
Attempts 5–6: further clean passes → last-3 all pass, MID absent → has_improved TRUE →
           counter deactivated, flag cleared, improved_ids=[C3-M01].
```

> **Remember this:** *“Twice in five, thrice ever, or twice across variants — then it’s recurring
> until three clean passes in a row.”*

---

## N — Adaptive engine

`[IMPLEMENTED]` — `packages/adaptive/policy.py` (R1–R8 assign integer priorities) +
`ranking.py` (pure sort) + `models.py` (typed I/O) + `reasons.py` (templates). Reads Step-8 views
only; never computes mastery; no DB/LLM/randomness.

### Decision tree (ACTUAL implementation order)

```text
For each concept (prereq pass first, then per-concept R2–R8):

Prerequisite mastery < 0.60?
  YES → REVIEW_PREREQUISITE (priority 100 + urgency; merges duplicates, highest wins;
        BLOCKS challenge+transfer for the downstream concept)
  NO ↓
Mastery < 0.40 (novice)?
  YES → REVIEW_CONCEPT (80) + REMEDIAL_PROBLEM (70)          [R2]
  NO ↓
Recurring misconception active?
  YES → REVIEW_CONCEPT / REMEDIAL targeting it (+15, reason says “Recurring weakness”)
        [R3; combines with whatever band-branch below]
  (continue) ↓
Mastery in [0.40, 0.60) (emerging)?
  YES → PRACTICE_PROBLEM (50)                                [R4]
  NO ↓
Mastery in [0.60, 0.80) (proficient)?
  YES → PRACTICE_PROBLEM (50) + TRANSFER_PROBLEM (40) when ready   [R5]
  NO ↓
Mastery ≥ 0.80 (mastered)?
  YES → CHALLENGE_PROBLEM (30) (+ TRANSFER when ready),
        SUPPRESSED when recurring / declining / hint-high     [R6]
Modifiers anywhere: declining trend → +10 to REVIEW/PRACTICE [R7];
                    hint dependence ≥ 0.50 → +10 to REVIEW + suppress CHALLENGE/TRANSFER [R8]
Priority = base + urgency_bonus + boosts; urgency = round((1-mastery)*10) (0..10).
```

### Action types / reason codes / priorities

- **Actions:** `REVIEW_CONCEPT (80)`, `REMEDIAL_PROBLEM (70)`, `PRACTICE_PROBLEM (50)`,
  `TRANSFER_PROBLEM (40)`, `CHALLENGE_PROBLEM (30)`, `REVIEW_PREREQUISITE (100)`.
- **Reason codes (9):** `PREREQUISITE_NOT_MASTERED, LOW_MASTERY, RECURRING_MISCONCEPTION,
  EMERGING_PRACTICE, PROFICIENT_PRACTICE, READY_FOR_TRANSFER, READY_FOR_CHALLENGE,
  DECLINING_TREND, HIGH_HINT_DEPENDENCE`.
- Review reason precedence: recurring > low-mastery > declining > hint-high (co-factors appended
  as suffix sentences without changing the code).
- Ranking: `rank_key = (-priority, concept_id, action, problem_id, reason_code, reason)` —
  stronger tier always wins; urgency only orders *within* a tier (never crosses tiers).

### Readiness gates (exact)

- **Transfer-ready** (`is_transfer_ready`): mastery ≥ 0.60 AND `attempt_count ≥ 2` (`TRANSFER_MIN_ATTEMPTS`)
  AND hint < 0.50 AND trend ≠ declining AND no recurring misconception for the concept. Also suppressed
  when `blocked` (prereq gate) or hint-high (wants_transfer requires proficient+ AND not blocked AND not hint-high).
- **Challenge-ready** (`is_challenge_ready`): mastery ≥ 0.80 AND hint < 0.50 AND not declining AND no
  recurring. Problem pick: hardest-first (difficulty desc, id asc); prefers difficulty ≥ 4 when the
  catalog allows; other roles pick easiest-first (difficulty asc, id asc) with easiest-canonical fallback.
- **Prerequisites** (`evaluate_all` R1): per concept, each listed prereq with known state and mastery
  < threshold (per-prereq `mastery_threshold`, default `0.60`) ⇒ one `REVIEW_PREREQUISITE` on the prereq
  concept (priority 100 + its urgency); downstream concept gets `blocked=True`. Missing prereq state ⇒
  skipped (never invent a violation). Duplicate prereq actions merged (highest wins).
- **Track safety:** request `language_track` must be supported; concept states carrying a different track
  ⇒ `ValueError` (“tracks must not cross”); duplicate concept states ⇒ `ValueError`.

### Why adaptive decisions are deterministic

Same `(states, misconceptions, curricula, problems, track)` ⇒ same recommendations, byte-identical
reasons included (tests assert order-invariance and determinism). There is no model call, no sampling,
no clock: priorities are closed-form arithmetic and the sort key is total. That makes the roadmap
explainable (“why this problem?” → the reason string cites mastery value, band, trend, hint rate,
recurrence counts) and testable (golden expectations per band).

### How learner history affects future problems

History enters as numbers, never prose: mastery (band branch), `attempt_count` (transfer gate),
`hint_dependence` (R8 + gates), `trend` (R7 + gates), `recent_pass_rate` (evidence text),
recurring flags + `occurrence/recent/variant` counts (R3 + boosts + gates), transfer rates (readiness
wording). Weaker mastery adds urgency (+0..10) so weaker concepts surface first within a tier.

> **Remember this:** *“Prereqs first, then band, then recurrency; declining and hint-dependence pump
> the brakes; transfer and challenge are earned, not given.”*

---

## O — Verification engine

`[IMPLEMENTED]` — `packages/verification/engine.py` (pure; no execution/DB/LLM/mastery/adaptive).

### Why verification exists

Solving the original problem again proves **recall of one fix**. Solving a *different* problem that
needs the *same skill* proves **transfer of understanding**. Verification exists to separate the two,
so Cognify never advances a student on a memorized patch.

### PASS vs VERIFIED_IMPROVED

- **PASS** = one execution outcome (all tests green on one problem). Owned by the execution service.
- **VERIFIED_IMPROVED** = a *pair* verdict: original-retry PASS **and** transfer PASS under one shared
  scope (same concept/track, linked problems, named target misconception). Owned by the verification
  engine. The reason text explicitly disclaims mastery: “VERIFIED_IMPROVED for this
  intervention/concept instance … verified-improvement evidence, not concept mastery (mastery remains
  owned by Step 8).”

### All outcomes + decision table (verbatim from `engine.py`)

```text
Original retry | Transfer   | Outcome            | Reason code
missing        | missing    | INCOMPLETE         | ORIGINAL_RETRY_MISSING
missing        | any        | INCOMPLETE         | ORIGINAL_RETRY_MISSING
non-PASS       | any        | NOT_IMPROVED       | ORIGINAL_RETRY_FAILED
PASS           | missing    | INCOMPLETE         | ORIGINAL_RETRY_PASSED_TRANSFER_MISSING
PASS           | non-PASS   | SURFACE_FIX        | ORIGINAL_RETRY_PASSED_TRANSFER_FAILED
PASS           | PASS       | VERIFIED_IMPROVED  | ORIGINAL_AND_TRANSFER_PASSED
```

Only `PASS` counts as passing: `FAIL / COMPILE_ERROR / RUNTIME_ERROR / TIMEOUT` are all non-passing.
Partial evidence, confidence scores, and hint levels never influence the verdict. `intervention_level`
is carried but never changes the verdict. Scope validation: concept/track must agree everywhere;
`transfer_problem_id` must differ from original; `is_transfer` flags must agree with roles;
isomorphic groups must agree when supplied; misconception must belong to the concept.

### Why solving the original problem is not enough

`SURFACE_FIX` is the cautionary tale: PASS on the retry + non-PASS on transfer means the student
patched the instance without repairing the mental model (e.g. hardcoded the failing case). The closed
loop then records the transfer **failure** against the target (with `verification-target:<MID>` ref)
so the learner model and adaptive engine react accordingly — instead of celebrating prematurely.

> **Remember this:** *“One green tick is a hint; two green ticks on two stories is evidence.”*

---

## P — Closed loop

`[IMPLEMENTED]` — `services/core-backend/app/closed_loop.py` (953 lines). It **orchestrates**;
it duplicates no logic (verification decides, learner records, adaptive recommends — this file
just calls them in the right order with validated context).

### Sequence diagram (what actually happens on a transfer submission)

```mermaid
sequenceDiagram
    participant S as Student
    participant CB as student.py
    participant EX as Execution Service
    participant EV as Evidence/Diagnosis
    participant LM as learner_engine
    participant TP as Transfer+Verification
    participant CL as closed_loop
    participant AD as Adaptive Engine
    S->>CB: POST /student/submissions (canonical code)
    CB->>EX: execute vs public+hidden tests
    EX-->>CB: FAILED + decisive test
    CB->>EV: build pack → diagnose (C3-M01) → intervene
    CB->>LM: record_attempt(passed=False, C3-M01)
    CB-->>S: feedback + retry guidance
    S->>CB: retry (fixed code)
    CB->>EX: execute → PASSED (stash, unlock transfer)
    S->>CB: transfer code
    CB->>EX: execute → PASSED/FAILED
    CB->>TP: VerificationContext → verify_improvement
    CB->>CL: run_closed_loop(session, context)
    CL->>LM: record_attempt × N (per plan_records)
    CL->>AD: recommend_next_actions on fresh views
    CL-->>CB: ClosedLoopResult
    CB-->>S: verification + recommendations + journey_state
```

### Verification → learner mapping (from `closed_loop.py` docstring — memorize)

| Verification outcome | Attempts recorded | Learner semantics |
|---|---|---|
| `VERIFIED_IMPROVED` | **2**: clean canonical pass + transfer pass (`is_transfer=True`), no diagnosed MID, target MID carried in `evidence_refs` as `verification-target:<ID>` | Full success evidence; transfer counters increment. |
| `SURFACE_FIX` | **2**: clean canonical pass + transfer **failure** with target attached | Retry succeeded but transfer failed — model learns the fix didn’t generalize. |
| `NOT_IMPROVED` | **1**: only the failed canonical with target; transfer NOT recorded | No transfer evidence exists (retry failed), so nothing transfer-related is written. |
| `INCOMPLETE` | **0**, zero recommendations, reason `Verification evidence is incomplete; learner state was not mutated.` | Nothing happened yet (missing retry/transfer) — state untouched. |

Details: `plan_records` is pure (DB-free) and deterministic; iso group falls back to
`CLOSED-LOOP-{concept}-{problem_id}` when the context carries none; `EXECUTION_STATUS_FOR_OUTCOME`
maps `PASS/FAIL/COMPILE_ERROR/RUNTIME_ERROR/TIMEOUT → PASSED/FAILED/COMPILE_ERROR/RUNTIME_ERROR/TIMEOUT`;
`run_closed_loop` validates journey existence + user match + track match (else `ValueError`),
requires a real `VerificationContext` (else `TypeError`), then records each plan via
`learner_engine.record_attempt`, snapshots `LearnerStateSnapshot`, and calls
`recommend_next_actions` with catalog problems + taxonomy curriculum. Re-running re-records
(append-only, no dedup key) — `[PARTIALLY IMPLEMENTED]` idempotency, honestly stateless.

### What closed-loop orchestration does NOT own

It does not execute code, build evidence, diagnose, compute mastery, detect recurrence, rank, or
persist by itself — it calls the owners for each. It never claims “mastery achieved”
(`build_closed_loop_reason` is deterministic prose over recorded attempts + snapshot).

> **Remember this:** *“The closed loop is a conductor, not an orchestra — it cues verification,
> learner, and adaptive in order and writes down what happened.”*

---

## Q — Problem bank

### Schema (`packages/problem_schema/models.py`) `[IMPLEMENTED]`

Each problem JSON carries: `problem_id, concept_id (C1–C8, UPPER-known), language (python|java),
difficulty (int 1–5, bool rejected), title, description, constraints (≥1), starter_code (verbatim,
non-empty), input_format, output_format, public_tests (≥1), hidden_tests (≥0),
test IDs matching `^[A-Za-z0-9][A-Za-z0-9._-]*$` and unique across public+hidden,
isomorphic_group_id, variant_role (canonical|transfer|remedial), misconception_ids (≥1, unique,
known, all belonging to the concept)`. Helpers: `all_tests()` (public first), `test_ids()`,
`is_valid_variant_role / is_valid_difficulty`.

### Canonical vs remedial vs transfer vs isomorphic group

- **Canonical:** the main teaching problem for a concept slice (difficulty usually 2).
- **Remedial:** own isomorphic group, difficulty 1, razor-focused probe for ONE misconception
  (e.g. Sum-One-to-N exposes `range(1,n)` vs `range(1,n+1)` with the `n=1` razor: buggy gives 0, correct gives 1).
- **Transfer:** SAME `isomorphic_group_id` + same misconceptions + same difficulty as its canonical,
  but a **different surface story and input shape** — “same loop-bounds and accumulator skill,
  different story and filter predicate”. Functional cross-checks prove neither variant solves the other
  (reference solutions fail cross-run; e.g. copying the temperature formula cannot produce hours-from-minutes).
- **Isomorphic group:** the skill-identity string (e.g. `ISO-C3-COUNT-DIV`) shared by canonical +
  transfer; the ONLY thing that lets R3 count “same mistake, different story”.
- **Misconception mapping:** each problem lists the MIDs it can expose (canonical/transfer usually 2,
  remedial 1–2); diagnosis candidates come from this list.
- **Public tests (2 each):** shown with input/expected/got on failure.
- **Hidden tests (3 each):** counted but redacted (counts + generic guidance only).
- **Canonical reference solution (`*_canonical.py`):** DATA ONLY — docstring states it is NEVER executed
  by the pipeline; student code runs only in the Docker sandbox.
- **Validation:** `Problem.from_dict` enforces everything above; `loader` adds sorted discovery +
  duplicate-ID rejection; `test_step19` asserts all 24 problems satisfy difficulty ∈ {1,2,3},
  python-scoped MIDs, rule-target disjointness for non-C3, and bidirectional transfer distinctness.

### Current problem bank by concept (24 problems — counted from `problem-bank/python/`, do not invent)

| Concept | Canonical (group / MIDs / diff) | Transfer (same group / MIDs / diff) | Remedial (own group / MIDs / diff) |
|---|---|---|---|
| C1 | `PY-C1-TEMP-CONVERT` Fahrenheit→Celsius (`ISO-C1-TEMP-CONVERT` / C1-M02,C1-M03 / 2) | `PY-C1-TEMP-CONVERT-TRANSFER` Hours-From-Minutes (same / C1-M02,C1-M03 / 2) | `PY-C1-AVG-PAIR` Average-of-Two (`ISO-C1-AVG-PAIR` / C1-M02 / 1) |
| C2 | `PY-C2-GRADE-BAND` Grade-Band (`ISO-C2-GRADE-BAND` / C2-M01,C2-M03 / 2) | `PY-C2-GRADE-BAND-TRANSFER` Parcel-Ship-Class (same / C2-M01,C2-M03 / 2) | `PY-C2-EITHER-OR` Either-Or (`ISO-C2-EITHER-OR` / C2-M01 / 1) |
| C3 | `PY-C3-COUNT-DIV` Count-Divisible (`ISO-C3-COUNT-DIV` / C3-M01,C3-M04 / 2) | `PY-C3-COUNT-DIV-TRANSFER` Count-Cold-Days (same / C3-M01,C3-M04 / 2) | `PY-C3-LOOP-MISCONCEPTION` Sum-One-to-N (`ISO-C3-INCLUSIVE-SUM` / C3-M05 / 1) |
| C4 | `PY-C4-RECT-METRICS` Rect-Area-Perimeter (`ISO-C4-RECT-METRICS` / C4-M03,C4-M04 / 2) | `PY-C4-RECT-METRICS-TRANSFER` Box-Volume-Surface (same / C4-M03,C4-M04 / 2) | `PY-C4-DOUBLE-IT` Double-It-Function (`ISO-C4-DOUBLE-IT` / C4-M03 / 1) |
| C5 | `PY-C5-FIND-MAX` Find-Maximum (`ISO-C5-FIND-MAX` / C5-M01,C5-M04 / 2) | `PY-C5-FIND-MAX-TRANSFER` Longest-Word (same / C5-M01,C5-M04 / 2) | `PY-C5-LAST-ITEM` Last-List-Item (`ISO-C5-LAST-ITEM` / C5-M01 / 1) |
| C6 | `PY-C6-COUNT-WORD` Count-Word (`ISO-C6-WORD-COUNT` / C6-M01,C6-M05 / 2) | `PY-C6-COUNT-WORD-TRANSFER` Stock-Totals (same / C6-M01,C6-M05 / 2) | `PY-C6-SAFE-LOOKUP` Safe-Price-Lookup (`ISO-C6-SAFE-LOOKUP` / C6-M01 / 1) |
| C7 | `PY-C7-BANK-ACCOUNT` Bank-Ledger (`ISO-C7-BANK-ACCOUNT` / C7-M01,C7-M02 / 3) | `PY-C7-BANK-ACCOUNT-TRANSFER` Shopping-Cart (same / C7-M01,C7-M02 / 3) | `PY-C7-COUNTER` Simple-Counter (`ISO-C7-COUNTER` / C7-M02,C7-M05 / 2) |
| C8 | `PY-C8-FACTORIAL` Recursive-Factorial (`ISO-C8-FACTORIAL` / C8-M01,C8-M03 / 2) | `PY-C8-FACTORIAL-TRANSFER` Recursive-Power (same / C8-M01 / 3) | `PY-C8-RECURSIVE-SUM` Recursive-Sum-to-N (`ISO-C8-RECURSIVE-SUM` / C8-M01 / 1) |

Every problem: **2 public + 3 hidden = 5 tests** (verified across the bank). All Python.
`problem-bank/java/` does not exist `[PLANNED / NOT IMPLEMENTED]`.

> **Remember this:** *“Transfer = same skill, new story. If you can copy-paste the old answer, it
> isn’t transfer — ours is cross-checked so you can’t.”*

---

## R — Frontend

`[IMPLEMENTED]` for the C3 demo slice; Learn/Progress/History/Home render real learner state
from the read-only Step 20B endpoints (non-C3 concepts honestly report “Not started yet” until
they have attempts). Stack: **Next.js 16 + React 19 + Tailwind 4** (`apps/web/package.json`),
Vitest + jsdom + Testing Library for tests, empty `next.config.ts`.

### Architecture (current, verified)

- **API client** (`app/lib/api.ts`): 7 typed wrappers over core-backend ONLY —
  `createSession / submit / getJourney / getProblem / getConcepts / getHistory / getProblems`;
  base URL `NEXT_PUBLIC_CORE_BACKEND_URL ??
  http://localhost:3000→http://localhost:8000`. `ApiError` + `friendlyError` map 0→“Backend
  unreachable”, 409→“Finish the current problem…”, 503→“execution unavailable”. No intelligence.
- **Routes (5):** `/` Home (“what next”: ContinueCard + backend-`next_action` NextStepCard with
  journey fallback + “Where you stand” + “Recent activity”, enrichment best-effort) ·
  `/learn` roadmap (all 8 concepts from `GET /student/concepts`, grouped by backend `group`) ·
  `/practice` editor + results (unchanged Step 20A flow) ·
  `/progress` per-concept cards (level/trend/attempts/transfer/hints + `next_action`) ·
  `/history` real attempt list from `GET /student/history` (honest empty state when none).
- **Session** (`components/session.tsx`): throwaway per-browser id in
  `localStorage["cognify.session_id"]`; `boot()` creates or resumes (`getJourney` + problem enrich;
  404 ⇒ fresh “session expired”); `refresh/restart/startFresh`. Explicitly NOT auth.
- **Practice flow** (`app/practice/page.tsx` + `components/practice.tsx`): starter-code init;
  client guards (empty / >100k mirrored cap); `requestId` guard so only the newest submit renders;
  `ProblemPanel` + `CodeEditor` (textarea, Cmd/Ctrl+Enter, “Running…”); `ResultPanel` branches —
  canonical-PASS (“Good improvement” + Continue-to-transfer), transfer+verification (verified ⇒
  “Verified improvement” + mastery note + top-3 recommendations), FAILED (`FailedFeedback`: passed
  X/Y, hidden-aware TestList, certainty heading likely/possible/uncertain, explanation,
  `InterventionCard` with `student_message` + `recommended_action`, Retry), error statuses
  (TIMEOUT ⇒ “took too long — check for loop that never ends”). `role="alert"` + `aria-live="polite"`,
  result focus management.
- **Humanization** (`app/lib/copy.ts`): `stripCodes` rewrites `C3-M01→“this idea”` and
  `SCREAMING_SNAKE→“this step”`; `humanizeReason` turns rule/adaptive reasons into student prose;
  raw IDs surface only under `?debug=1` (`DebugDetails`). Static `concepts.ts` map is display-only.
- **Error handling:** field-level (empty/long code), transport-level (friendlyError), session-level
  (“Couldn’t start your session” + Try again), execution-level (503 copy). CORS-tested backend
  allowlist backs it.

### Incomplete parts (marked in code — do NOT present as done)

| Area | State |
|---|---|
| History page | `[IMPLEMENTED]` — real attempt list from `GET /student/history`; honest empty state when no attempts. |
| Learn/Progress for C1–C2, C4–C8 | `[IMPLEMENTED]` (read views) — all 8 concepts served by `GET /student/concepts`; zero-attempt concepts honestly report “Not started yet”. Practice remains C3-scoped. |
| Java track UI | `[PLANNED / NOT IMPLEMENTED]` — header hardcodes “current language: Python”. |
| Auth / accounts / roles | `[PLANNED / NOT IMPLEMENTED]` — sessions are throwaway browser tokens. |

> **Remember this:** *“The frontend is a faithful messenger: seven read/submit endpoints, no
> opinions, honest empty states where no learning has happened yet.”*

---

## S — Security

Only implemented measures are listed (each with WHAT/WHY/HOW). Anything else is marked.

| # | Measure `[status]` | WHAT | WHY | HOW (file evidence) |
|---|---|---|---|---|
| 1 | Server-side execution `[IMPLEMENTED]` | Student code runs in execution-service, never in browser/core-backend/AI. | Untrusted code must not share a process with state/secrets. | `student._default_runner_factory` raises instead of local-run; only `httpx` crosses the boundary. |
| 2 | Docker isolation `[IMPLEMENTED]` | One container per run + helper container for files + named temp volume. | Contain filesystem/process damage; no host bind-mount confusion. | `sandbox.py`: `docker run --rm`, helper image `python:3.11-slim`, volume `cognify-exec-vol-<hex>`, `--rm` + `kill` + `volume rm` cleanup. |
| 3 | Network disabled `[IMPLEMENTED]` | No egress from student/helper containers. | Block exfiltration, C2, package installs, oracle attacks. | `--network none` (helper hardcoded; student default `none`); tests assert flags, forbid `-e/--env`. |
| 4 | Resource limits `[IMPLEMENTED]` | Memory 256m (+swap), CPU 1.0, PIDs 128, per-test timeout 1–30 s (slice 5 s). | Stop fork-bombs, miners, infinite loops from starving the host. | `sandbox` constants + `build_command`; `models` timeout bounds; timeout→kill→`TIMEOUT` result. |
| 5 | Code size limits `[IMPLEMENTED]` | ≤100k chars (both services), 1–50 tests/request. | Bound payload/Docker-stdin abuse. | `student.MAX_CODE_CHARS`, `models.MAX_CODE_CHARS/MAX_TESTS_PER_REQUEST`; 422 on violation. |
| 6 | Hidden-test redaction `[IMPLEMENTED]` | Hidden expected/actual/inputs never leave the server. | Prevent answer harvesting via UI/devtools. | `problem_view` allowlist; `to_student_view` (`expected_output→None`, `hidden_redacted`); 2000-char truncation; UI “details stay hidden”. Step 20B extends the same philosophy: concept views omit mastery floats + misconception IDs + iso groups + evidence refs; history omits outputs/IDs/groups/refs; the catalog omits tests/MID bindings/iso/solutions and scrubs MID mentions from bank descriptions (`_safe_description`). |
| 7 | Server-side problem resolution `[IMPLEMENTED]` | Tests/concept/language/group resolved from `problem_id` server-side. | Client must not pick its own grading truth. | `_resolve_problem` + bank loader; request models drop unknown fields. |
| 8 | Spoofing protection `[IMPLEMENTED]` | Client concept/language/mastery/diagnosis/verification ignored. | Stop crafted “I already mastered this” payloads. | `extra="ignore"` + resolution-only flow; spoof test (`C8/java/1.0` still `FAILED+C3-M01`). |
| 9 | Timeout + cleanup `[IMPLEMENTED]` | Wall-clock kill + container/volume removal (best-effort, 10 s caps). | No orphan containers/volumes filling the daemon. | `subprocess.run(timeout=…)` → `_kill_container` → `finally _remove_volume`; `--rm` everywhere. |
| 10 | Fail-closed `[IMPLEMENTED]` | Docker/HTTP failure ⇒ 503/502, never local execution or fake PASS. | A degraded grader must refuse, not invent grades. | `SandboxUnavailableError` → 503 chain; `BadResponse` → 502; `PWNED`-probe test. |
| 11 | CORS allowlist `[IMPLEMENTED]` | Only configured web origins may call the API with credentials. | Reduce cross-site abuse surface. | `STUDENT_CORS_ORIGINS` (default `localhost:3000`); evil-origin test. |
| 12 | API validation `[IMPLEMENTED]` | Strict shapes + taxonomy belonging + agreement checks. | Reject malformed/mixed-scope requests early. | Pydantic + `repositories` normalizers + `passed⇔PASSED` + track checks; scrubbed error bodies. |
| 13 | Secret hygiene `[IMPLEMENTED]` (partial) | No hardcoded keys; secrets from env; metadata scrubbed from evidence/events. | Avoid leaking keys into logs/DB/UI. | `LLM_API_KEY` env-only; `sanitize_metadata`; secret-fragment rejection in `RelevantEventEvidence`; no-`sk-` tests. |
| 14 | AuthN/AuthZ | `[PLANNED / NOT IMPLEMENTED]` — no users/passwords/JWT enforcement in code (`JWT_SECRET` env is scaffold). Anyone with the URL can create sessions. Say so in viva. |
| 15 | Per-user isolation | `[PARTIALLY IMPLEMENTED]` — sessions isolated in-process, but all share one process/daemon with no CPU/memory quotas per user and no persistent ownership. True multi-tenant isolation needs auth + DB + quotas. |
| 16 | Stronger sandboxes (gVisor/Firecracker/K8s/seccomp profiles) | `[PLANNED / NOT IMPLEMENTED]` — none in code. Current trust boundary is Docker flags + fail-closed. |

> **Remember this:** *“Untrusted code gets a locked, timed, network-less room — and if we can’t
> lock the room, we refuse to run.”*

---

## T — Data flow chart (entire pipeline, one diagram)

```mermaid
flowchart TB
    FE["Frontend<br/>Next.js: session, editor, results"]
    SE["Session<br/>localStorage id + journey enrich"]
    PB["Problem Bank<br/>24 Python problems, ISO groups"]
    SUB["Submission<br/>POST /student/submissions"]
    CB["Core Backend :8000<br/>resolve, orchestrate, own state"]
    EC["Execution Client<br/>httpx + validate, fail-closed"]
    EX["Execution Service :8002<br/>validate, compile, run tests"]
    DK["Docker Sandbox<br/>helper vol + student run<br/>none/256m/1CPU/128pids"]
    EV["Evidence<br/>EvidencePack observed"]
    DG["Diagnosis<br/>rules 0.70 → LLM → fallback"]
    IN["Intervention<br/>L1-L4 + type/skill"]
    LM["Learner Model<br/>record_attempt, counters, flags, events"]
    MA["Mastery<br/>formula + bands + trend"]
    MI["Misconceptions<br/>counters + R1/R2/R3 + improvement"]
    VF["Verification<br/>PASS+PASS ⇒ VERIFIED_IMPROVED"]
    AD["Adaptive Engine<br/>R1-R8 + ranking"]
    RC["Recommendation<br/>action + reason + problem"]

    FE --> SE --> PB --> SUB --> CB --> EC --> EX --> DK --> EX --> CB --> EV --> DG --> IN --> CB
    CB --> LM --> MA
    LM --> MI
    CB --> VF --> LM
    LM --> AD --> RC --> FE
```

Read it as: UI bootstraps a session, the bank supplies truth, the submission crosses into the
backend, execution happens behind an HTTP boundary inside Docker, results come back as evidence,
diagnosis names the cause, intervention teaches it, the learner model remembers (mastery +
misconceptions), verification proves transfer, adaptive ranks what’s next, and the recommendation
lands back in the UI. State lives only in `LM`; reasoning only in `DG`; execution only in `DK`.

---

## U — “Who does what?” table (memorize before review)

| Component | Main Responsibility | Does NOT Do |
|---|---|---|
| Frontend | Session bootstrap, problem display, code editing, result/feedback/recommendation rendering, honest placeholders. | No grading, no diagnosis, no mastery math, no decisions (4 endpoints only). |
| Core Backend | Owns sessions + learner state; orchestrates resolve→execute→evidence→diagnose→record→intervene→verify→recommend. | Never executes student code; never lets the LLM write state. |
| AI Service | Reasons about ONE EvidencePack: rules → LLM → fallback, validated + gated, then builds an intervention. | No DB, no mastery, no ranking, no execution, no memory between calls. |
| Execution Service | Runs untrusted code vs tests in Docker and aggregates 5 statuses. | No grading opinions, no learner state, no problem selection. |
| Learner Model | Remembers everything: mastery, attempts, hints, transfers, counters, flags, events. | No math of its own (delegates to formula/weakness), no pedagogy. |
| Mastery Formula | Pure arithmetic: previous + gain/penalty + momentum → clamp + round; bands + trend + rates. | No DB, no history lookup (caller supplies `recent_pass_rate`). |
| Diagnosis Rules | Exact C3 pattern matchers (code-AST + uniform dynamic signature), self-validated. | No LLM call, no guessing outside their predicates (abstain otherwise). |
| Adaptive Engine | Deterministic R1–R8 next-action policy + ranking + reason strings. | No mastery computation, no LLM, no state. |
| Verification Engine | Pair verdict over retry + transfer (PASS+PASS ⇒ VERIFIED_IMPROVED). | No execution, no mastery, no “who to teach next”. |
| Problem Bank | Versioned skill truth: canonical/remedial/transfer, tests, groups, MID mapping, reference solutions. | Never executes anything (canonical files are data-only). |
| Taxonomy | Controlled vocabulary: C1–C8, 48 MIDs + 5 X-*, prerequisites, language scope. | No behavior — everything else validates against it. |

---

## V — Why did we design it this way?

| Decision | Why | Alternative | Why not the alternative |
|---|---|---|---|
| Separate AI service? | Isolate probabilistic reasoning behind a validated I/O contract; scale/throttle/replace models without touching learner state. | LLM calls inline in core-backend. | A model hiccup could then corrupt grading/state; separation + bans make the blast radius zero. |
| Deterministic adaptive engine? | Roadmap decisions must be explainable (“mastery 0.42 ⇒ practice”) and reproducible for review/testing. | LLM picks the next problem. | Non-deterministic, untestable, prompt-sensitive; same history could yield different roadmaps. |
| Learner model (persistent)? | Recurrence, momentum, hint-dependence, and transfer need memory across attempts; events make every number auditable. | Stateless pass/fail. | Same mistake forever looks “new”; no R1/R2/R3, no trend, no verification history. |
| Evidence pack? | Forces diagnosis to cite observations; one schema serves rules, LLM, fallback, and audit. | Pass code+stderr to the LLM raw. | Unstructured guessing, hallucinations, no reproduciblity, secrets risk. |
| Transfer problems? | Distinguish memorized patches from repaired mental models (the `SURFACE_FIX` trap). | More retries of the same problem. | Students can overfit one instance; no generalization signal. |
| Verification? | A fixed pair-decision table stops premature celebration; both attempts are recorded either way. | “Retry PASS ⇒ mastered”. | Inflates mastery on surface fixes; adaptive advances on sand. |
| Docker sandbox? | Untrusted code needs OS-level containment with no-network + caps + guaranteed cleanup. | In-process `exec`/subprocess on host. | Arbitrary code execution on the grading host; one `os.system` ends the demo (and worse). |
| Server-side problem resolution? | Grading truth (tests, concept, group, answers) must never reach the client. | Frontend sends tests/expected with code. | Trivial spoofing + hidden-test harvesting via devtools. |
| Not letting LLM decide mastery? | Numbers must be closed-form and auditable; model arithmetic is unreliable and untestable. | “LLM, update mastery to what feels right.” | Corrupted state, no determinism, no viva-defensible formula. |
| Not simply using ChatGPT? | ChatGPT lacks execution grounding, memory, transfer proof, and deterministic adaptation — the four things Cognify exists for. | Generic AI feedback box. | Hallucinated diagnoses, no recurrence tracking, no verified improvement. |
| Not one monolith backend? | Execution (unsafe), reasoning (probabilistic), and state (must-be-safe) have opposing failure modes; boundaries let each fail safely (503 vs fallback vs untouched state). | Single FastAPI app. | One bug compromises everything; cannot scale/harden pieces independently. |
| Separate execution service? | Puts a validated HTTP contract + fail-closed semantics between untrusted code and learner state. | Library call into a runner. | Loses the bulkhead; local-fallback temptation during outages (explicitly tested against). |

---

## W — Company-style questions

> Format per question: **QUESTION** · **WHAT THE INTERVIEWER IS TESTING** · **GOOD ANSWER**
> (truthful to current code) · **KEY POINTS TO REMEMBER** · **COMMON WRONG ANSWER**.
> All answers verified against the implementation on 2026-09-20.

### LEVEL 1 — Basic

**W1.1 — What is Cognify?**
- Testing: can you state the idea in one breath.
- Good answer: “An evidence-grounded, closed-loop programming tutor: it executes student code in a
  Docker sandbox, diagnoses the root-cause misconception from observed evidence, teaches that cause,
  requires retry + transfer, verifies improvement, remembers everything in a learner model, and
  deterministically recommends the next step.”
- Key points: execute → evidence → diagnose → intervene → retry → transfer → verify → adapt.
- Wrong answer: “An AI code explainer / a LeetCode clone with ChatGPT.”

**W1.2 — What problem does it solve?**
- Testing: problem-first thinking.
- Good answer: “Beginners fail for different underlying reasons but tools only say pass/fail, so
  students patch symptoms, nothing remembers recurrences, and nobody checks transfer. Cognify makes
  every failure produce evidence, every intervention cite it, and every improvement survive transfer.”
- Key points: symptoms vs causes; memory; transfer proof; adaptive sequencing.
- Wrong answer: “Students need more problems.”

**W1.3 — What is the main workflow?**
- Testing: end-to-end recall.
- Good answer: recite §A arrows with one line each; emphasize canonical PASS unlocks transfer and
  PASS+PASS verifies.
- Key points: transfer gate (409 otherwise); verification table.
- Wrong answer: skipping evidence/transfer/verification steps.

**W1.4 — What technologies are used?**
- Testing: stack awareness.
- Good answer: “Next.js 16 + React 19 + Tailwind 4 frontend; three FastAPI services (core :8000, AI
  :8001, execution :8002); pure-Python packages; SQLAlchemy + SQLite prototype store; Docker sandbox
  via CLI; httpx between services; Vitest + pytest suites.”
- Key points: ports; shared `requirements.txt`; single Dockerfile with build args.
- Wrong answer: “PostgreSQL, Kubernetes, LangChain…” (none in the running path).

**W1.5 — What is the role of the frontend?**
- Testing: boundary clarity.
- Good answer: “Faithful messenger: session bootstrap, problem/editor/results UI, top-3
  recommendations display, honest placeholders. Four typed endpoints, zero intelligence.”
- Key points: `api.ts` has exactly 4 functions; C3-only live surface.
- Wrong answer: “It computes mastery / calls the LLM.”

**W1.6 — What is the role of FastAPI?**
- Testing: framework understanding.
- Good answer: “Serves all three service APIs with pydantic validation: student slice + health
  (core), diagnose + health (AI), execute + languages + health (execution). Factories are injectable
  so tests swap runners/clients/stores.”
- Key points: `create_app` pattern; status-code discipline (404/409/422/502/503).
- Wrong answer: “It renders the UI / runs student code.”

**W1.7 — What is the role of Docker?**
- Testing: isolation mental model.
- Good answer: “Only the execution service uses Docker, via CLI: helper container stages files into
  a named volume; student container runs with `--network none`, 256m/1 CPU/128 PIDs; cleanup always.
  No Docker ⇒ fail closed (503), never host execution.”
- Key points: daemon socket mount; no gVisor/K8s anywhere.
- Wrong answer: “Docker runs the whole app / each microservice is a student sandbox.”

### LEVEL 2 — Architecture

**W2.1 — Why did you separate the services?**
- Testing: trade-off reasoning.
- Good answer: §V row 11/12 — opposing failure modes (unsafe execution vs probabilistic reasoning
  vs must-be-safe state) each get their own bulkhead, contract, and failure semantics.
- Key points: 503 vs fallback vs untouched-state; independent scaling/hardening.
- Wrong answer: “Microservices for the sake of it.”

**W2.2 — How does frontend communicate with backend?**
- Testing: concrete I/O knowledge.
- Good answer: “`fetch` from `api.ts` to core-backend only: `POST /student/sessions`,
  `GET /student/problems/{id}`, `POST /student/submissions`, `GET /student/journey`. Base URL from
  `NEXT_PUBLIC_CORE_BACKEND_URL`. Web never calls AI/execution directly.”
- Key points: session id in localStorage; friendlyError mapping.
- Wrong answer: “WebSocket / direct Docker calls.”

**W2.3 — How does core-backend talk to execution-service?**
- Testing: integration detail.
- Good answer: “`execution_client.execute_problem` builds `{language, code, tests, timeout}` and
  `httpx.post`s to `EXECUTION_SERVICE_URL + /execute` with timeout `max(10, t*(n+1)+10)`; response is
  deep-validated (counts vs per-test agreement, decisive mirroring); unreachable/5xx ⇒ 503,
  malformed ⇒ 502.”
- Key points: fail-closed; no local fallback (tested with `PWNED` probe).
- Wrong answer: “Shared function call / message queue.”

**W2.4 — Why doesn’t the AI service write learner state?**
- Testing: separation-of-powers principle.
- Good answer: “Model output is probabilistic; state must be reproducible and auditable. The ban is
  structural (`db.py` forbids AI imports; tests grep for violations) so a hallucination can never
  become a remembered fact — it must survive validation, gating, execution, and transfer first.”
- Key points: reasoner proposes, engine disposes.
- Wrong answer: “It will in the next sprint.”

**W2.5 — What is the role of the learner model?**
- Testing: state comprehension.
- Good answer: §K — per-concept mastery/band/trend/attempts/hints/transfers, per-misconception
  counters/flags, supporting problems/groups, append-only events; written only by `record_attempt`.
- Key points: memory + audit trail; read views feed evidence/adaptive/UI.
- Wrong answer: “It’s the LLM / a neural network.”

**W2.6 — What happens after code submission?**
- Testing: lifecycle mastery.
- Good answer: walk §F.2 branch diagram (fail→diagnose→record→intervene; pass→unlock;
  transfer→verify→closed-loop; error→safe record).
- Key points: 409 gate; 503/502 mapping; view truncation/redaction.
- Wrong answer: “It returns pass/fail.”

### LEVEL 3 — AI/ML

**W3.1 — Where exactly is AI used?**
- Testing: precision over hype.
- Good answer: “In exactly one place: mapping an EvidencePack to one misconception ID + explanation
  inside `diagnose_pack` — and only when deterministic C3 rules abstain AND an LLM is configured
  (default env leaves it unconfigured, so rules→fallback carry the demo). Everything else is rules/math.”
- Key points: default `LLM_PROVIDER=` empty ⇒ deterministic mode.
- Wrong answer: “AI grades / sets mastery / picks problems.”

**W3.2 — What does the LLM do / NOT do?**
- Testing: scope discipline.
- Good answer: “Does: propose the single most likely candidate MID with confidence/explanation/refs
  as strict JSON. Does NOT: touch DB, compute mastery, generate hints, plan roadmaps, see other
  student data (prompt explicitly forbids all four).”
- Key points: system prompt rule 7; temperature 0.0 + json_object.
- Wrong answer: “It tutors conversationally.”

**W3.3 — How do you prevent hallucinated diagnosis?**
- Testing: trust engineering.
- Good answer: “Candidate-only MIDs, concept equality, strict 5-key schema, confidence ≥ 0.50,
  failure-grounded refs, taxonomy belonging — five independent rejections, then deterministic
  fallback. Tests cover hallucinated/wrong-concept/ungrounded/extra-key cases.”
- Key points: validator + gate + fallback chain; `source` labeling.
- Wrong answer: “Careful prompting.”

**W3.4 — What is evidence-grounded diagnosis?**
- Testing: concept clarity.
- Good answer: §H + §I.1 — code-AST shape AND dynamic output signature must BOTH match (e.g.
  `len(X)-1` + uniform −1 on every failure); refs cite the decisive test; rules self-check through
  the same validator+gate as the LLM.
- Key points: static + dynamic conjunction; abstention when either is missing.
- Wrong answer: “The LLM reads the code.”

**W3.5 — How are misconceptions represented?**
- Testing: data modeling.
- Good answer: “Uppercase `C*-M**` IDs in `taxonomy/errors.py` (48 + 5 cross-cutting), each with
  name/description/language-scope/typical-signal; bound to problems, candidates, counters, flags,
  interventions, and adaptive states by exact ID.”
- Key points: normalized `strip().upper()` everywhere; belonging checks.
- Wrong answer: “Free-text labels.”

**W3.6 — How do you handle uncertain diagnosis?**
- Testing: graceful degradation.
- Good answer: “No silence: fallback returns the best history-informed candidate at capped
  confidence with `Fallback:` prefix and failure-citing refs; UI maps confidence to
  likely/possible/uncertain; low-confidence LLM output is gated into the same fallback.”
- Key points: always-200 DiagnoseResult; uncertainty is a number, not an apology.
- Wrong answer: “Return ‘I don’t know’.”

### LEVEL 4 — Adaptive learning

**W4.1 — How is mastery calculated?**
- Testing: formula recall.
- Good answer: write §L formula with constants from memory (0.12 base, 0.5 hint damping, +0.04
  transfer, severities 0/0.5/0.75/0.75/1.0, momentum ±0.04 scaled, clamp+round4); prior rate = last-5
  (0.5 if none); worked example 0.20→0.32 / →0.115.
- Key points: `passed⇔PASSED` agreement; reason strings.
- Wrong answer: “Passes divided by attempts.”

**W4.2 — Why isn’t mastery simply pass/fail?**
- Testing: modeling judgment.
- Good answer: “Binary ignores severity (FAIL −0.085 vs TIMEOUT −0.12), independence (hints halve
  gains), generalization (+0.04 transfer), and consistency (momentum ±0.02). A memorized retry-pass
  must not equal a transferred pass.”
- Key points: bands need gradation; adaptive tiers need ordering.
- Wrong answer: “It’s simpler.”

**W4.3 — How do you detect recurring misconceptions?**
- Testing: rule recall.
- Good answer: R1/R2/R3 with numbers (2-in-5 / 3-ever / 2-variants) + improvement (3 clean) + worked
  example from §M.
- Key points: current appended explicitly; variant = max distinct problems in ONE group.
- Wrong answer: “Count total failures.”

**W4.4 — What is hint dependence?**
- Testing: metric semantics.
- Good answer: “`hint_count/attempt_count` (0 when none); damps pass gains ×0.5 and deepens fail
  penalties −0.02; ≥0.50 boosts review +10 and suppresses transfer/challenge. Currently hints are
  tracked in the model but the student slice passes `hint_used=False` (no hint endpoint yet) —
  honest prototype gap.”
- Key points: independence matters; read-view clamps legacy inconsistencies.
- Wrong answer: “Number of hints shown.”

**W4.5 — What is transfer readiness?**
- Testing: gate logic.
- Good answer: “Mastery ≥ 0.60 AND ≥2 attempts AND hint < 0.50 AND not declining AND no recurring
  (plus not blocked). It gates TRANSFER_PROBLEM emission; challenge needs ≥0.80 with the same guards.”
- Key points: earned, not given; code `is_transfer_ready / is_challenge_ready`.
- Wrong answer: “After any pass.”

**W4.6 — How does the adaptive engine choose the next action?**
- Testing: policy walkthrough.
- Good answer: draw §N tree: R1 prereq gate (100, blocking) → R2 novice review+remedial →
  R3 recurring +15 → R4/R5 practice (+transfer when ready) → R6 challenge (guarded) → R7/R8
  modifiers → rank by `(-priority, concept, action, …)` → `explain_recommendations`.
- Key points: urgency never crosses tiers; problem pick easiest-first (challenge hardest-first).
- Wrong answer: “Highest mastery first.”

**W4.7 — Why are adaptive decisions deterministic?**
- Testing: principle + testability.
- Good answer: “Same inputs ⇒ byte-identical outputs (no model/clock/randomness); closed-form
  priorities + total sort key; every recommendation carries its reason + evidence. Reviewers and
  tests can assert exact expectations.”
- Key points: explainability = defensibility in viva.
- Wrong answer: “Deterministic is faster.”

**W4.8 — How does learner history affect future problems?**
- Testing: systems thinking.
- Good answer: “As numbers, never prose: mastery (band branch), attempts (transfer gate), hint rate
  (R8+gates), trend (R7+gates), recurrence counts (R3+boosts+gates), transfer rates (readiness
  wording), urgency ordering. Quote one path, e.g. declining + hint-high ⇒ review +10/+10, no
  challenge/transfer.”
- Key points: §N last paragraph.
- Wrong answer: “The LLM remembers the chat.”

### LEVEL 5 — System design

**W5.1 — What happens if the execution service goes down?**
- Testing: failure semantics.
- Good answer: “Submissions fail closed: connection/5xx ⇒ `ExecutionServiceUnavailable` ⇒ HTTP 503
  ⇒ ‘temporarily unavailable’ UI. No local grading, no fake PASS, no state mutation on that path.
  Health endpoints + compose make the outage visible.”
- Key points: 503 vs 502 distinction; `PWNED` test.
- Wrong answer: “Queue and retry later.” (no queue exists)

**W5.2 — What happens if Docker is unavailable?**
- Testing: depth of sandbox understanding.
- Good answer: §G.5 chain: probe fails ⇒ `SandboxUnavailableError` ⇒ 503 ⇒ refused grading.
  Helper failures map identically. Nothing executes on the host by design.
- Key points: “refusing to execute student code on the host” (exact message).
- Wrong answer: “Falls back to local Python.”

**W5.3 — What happens if the LLM gives an incorrect diagnosis?**
- Testing: defense in depth.
- Good answer: “Four nets: validator (schema/taxonomy), gate (confidence/grounding), transfer
  requirement (wrong cause ⇒ transfer likely fails ⇒ SURFACE_FIX recorded against the target),
  recurrence/improvement math (sustained passes clear bad flags). Worst case: one L1 nudge off-target,
  then evidence corrects it.”
- Key points: no single component is trusted alone.
- Wrong answer: “It can’t — the prompt is good.”

**W5.4 — What happens if the same submission is repeated?**
- Testing: idempotency honesty.
- Good answer: “Deterministic outputs (same diagnosis/intervention/views) but append-only records:
  each submit appends attempt/diagnosis/transition events and re-runs counters/formula. Re-running
  closed-loop re-records. Dedup keys are `[PLANNED / NOT IMPLEMENTED]` — say so.”
- Key points: determinism ≠ idempotency; duplicate-submission test expects same diagnosis, not one row.
- Wrong answer: “Duplicates are ignored.”

**W5.5 — How would this scale to 100,000 students?**
- Testing: honest scaling (no fabrication).
- Good answer: “Current prototype cannot: process-local sessions + per-session in-memory SQLite die
  with the process. Path: durable Postgres (schema already relational; `DATABASE_URL` reserved) +
  Redis/session store, execution-service replicas + job queue with per-job timeouts, AI caching
  (pack-hash ⇒ diagnosis) + rate limits, stateless core replicas behind a LB, per-user quotas,
  migrations/observability. State that as a plan, not a claim.”
- Key points: name what exists (relational schema, stateless packages) vs what doesn’t.
- Wrong answer: “Add more Docker / Kubernetes and it scales.”

**W5.6 — How would you introduce PostgreSQL?**
- Testing: migration reasoning.
- Good answer: “Set `DATABASE_URL` to a sync psycopg URL (current example uses asyncpg — incompatible
  with the sync engine, must change driver), run `init_db` + a migration tool (none exists yet —
  say so), move `StudentStore` from per-session memory engines to a shared engine + session table,
  keep `repositories`/`learner_engine` untouched (they take any `Session`).”
- Key points: engine-only change; flush/commit discipline already correct.
- Wrong answer: “Replace SQLite imports everywhere.”

**W5.7 — How would you handle authentication?**
- Testing: security roadmap honesty.
- Good answer: “Today: none (throwaway sessions). Plan: issue-based auth (e.g. JWT via gateway),
  bind `users.id` to real identities, scope every query by user, expire/revoke sessions, then put
  the read-only per-concept/history/problem endpoints (Step 20B, currently session-scoped) behind
  auth. `JWT_SECRET` env is scaffold only.”
- Key points: sessions ≠ accounts; the 20B read views must move behind auth next.
- Wrong answer: “We have JWT auth.”

**W5.8 — How would you isolate users?**
- Testing: multi-tenancy thinking.
- Good answer: “Today: in-process dict + separate memory DBs (no cross-reads, but shared fate).
  Real isolation: auth-scoped DB rows, per-user execution quotas + timeouts, per-request sandbox
  volumes (already per-request), no shared filesystem, rate limiting, secret-free evidence.”
- Key points: current isolation is logical, not resource-level.
- Wrong answer: “Docker already isolates users.”

**W5.9 — How would you support multiple languages / Java?**
- Testing: extension design.
- Good answer: “Execution already runs Java (image + `Main.java` + javac); missing: Java bank
  (`problem-bank/java/` absent), Java taxonomy surfacing in candidate lists (taxonomy HAS java MIDs
  — good), track-aware problem resolution + UI switcher, Java diagnosis rules (AST shape differs),
  severity/band calibration per language. Fix the double-compile inefficiency first.”
- Key points: taxonomy ready, bank/rules/UI not.
- Wrong answer: “Change the language field.”

**W5.10 — How would you support instructors?**
- Testing: product thinking without fabrication.
- Good answer: “No dashboard exists. Candidate read-only views over existing tables: class mastery
   heatmap (concept states), recurring-misconception leaderboard (flags+counters), evidence drill-down
   (`explain_mastery`), transfer success rates. All data already logged; needs auth + aggregation
   endpoints (extending the Step-20B read-view pattern).”
- Key points: propose, don’t claim.
- Wrong answer: “Use the progress page.”

### LEVEL 6 — Security

**W6.1 — Can a student execute arbitrary commands?**
- Testing: threat modeling.
- Good answer: “Only inside the sandbox: arbitrary Python/Java runs, but with no network, capped
  memory/CPU/PIDs, timeout kill, filename guards, no env forwarding, no shell. Host processes only
  ever run the fixed Docker CLI argv — no `shell=True`, no `eval`, asserted by AST tests.”
- Key points: arbitrary *code*, contained *effect*.
- Wrong answer: “No — we filter bad keywords.”

**W6.2 — Can student code access the internet / host files?**
- Testing: containment specifics.
- Good answer: “No internet (`--network none` both containers). No host files (named volume only,
  relative filenames, no `..`/absolute, volume removed afterwards). Daemon socket is mounted for the
  service, not into student containers.”
- Key points: quote flags; cleanup guarantees.
- Wrong answer: “Firewall rules.” (none in code)

**W6.3 — Can a student see hidden tests?**
- Testing: redaction.
- Good answer: “No: `problem_view` allowlists safe fields; `to_student_view` nulls hidden expected
  outputs and flags `hidden_redacted`; top-level pointers stay `None` for hidden decisive tests; UI
  renders ‘details stay hidden’; regression tests grep responses for leaks.”
- Key points: three independent redaction layers.
- Wrong answer: “They’re obfuscated.”

**W6.4 — Can the frontend spoof a problem ID / mastery?**
- Testing: trust boundaries.
- Good answer: “Problem IDs outside the journey/role/language are rejected (404/422); all grading
  truth is re-resolved server-side; extra body fields are dropped — the spoof test sends
  `C8/java/1.0` and still gets `FAILED + C3-M01`. The only attacker-controlled grading input is code.”
- Key points: allowlist models + resolution-only flow.
- Wrong answer: “We check a signature.” (no signatures exist)

**W6.5 — How are execution resources limited?**
- Testing: numbers recall.
- Good answer: “100k code chars, ≤50 tests, 1–30 s timeouts (5 s slice), 256m RAM+swap, 1.0 CPU,
  128 PIDs, no network, 2000-char view truncation, 10 s helper/kill/volume caps.”
- Key points: recite the §G.2 table.
- Wrong answer: vague “Docker limits”.

**W6.6 — What happens when execution times out?**
- Testing: timeout path.
- Good answer: “`subprocess.TimeoutExpired` ⇒ kill container ⇒ `TIMEOUT` result with
  `TIMEOUT: exceeded {s}s wall-clock limit.` ⇒ status precedence makes the whole submission
  `TIMEOUT` ⇒ mastery −0.12 (harshest), recorded with `diagnosed=None`, UI says ‘took too long —
  check for loop that never ends’. Cleanup still runs.”
- Key points: severity 1.0; safe message, no diagnosis claim.
- Wrong answer: “It retries.”

### LEVEL 7 — Challenge questions (expose weaknesses; answer honestly)

**W7.1 — Why should we trust your diagnosis?**
- Testing: epistemic humility.
- Good answer: “Provisionally: C3 rules demand static+dynamic conjunction and self-validate; the LLM
  path needs validator+gate; fallback is history-informed, not random; every claim cites refs; and
  transfer decides whether we believed correctly. Current limit: only 2 C3 rules are exact — the rest
  rides fallback/LLM. Trust the *process*, verify via transfer.”
- Key points: process-over-oracle framing; admit C3-only exactness.
- Wrong answer: “99% accuracy.” (no such metric exists)

**W7.2 — How do you know Cognify actually improves learning?**
- Testing: evaluation honesty.
- Good answer: “We don’t yet — no classroom study, no benchmark suite in repo. What we HAVE is the
  mechanism: transfer-gated verification + recorded improvement trails that make a future study
  measurable (transfer success rate, recurrence clearance, mastery deltas). Propose the study; don’t
  claim the result.”
- Key points: mechanism exists, evidence of efficacy doesn’t.
- Wrong answer: inventing learning-gain statistics.

**W7.3 — What if the student memorizes the answer?**
- Testing: adversarial thinking.
- Good answer: “Retry-pass alone unlocks but doesn’t verify; the transfer variant (new story, new
  inputs, cross-checked unsolvable by copying) catches it as SURFACE_FIX, which the model records
  against the target and adaptive reacts to. Memorization is a first-class failure mode here.”
- Key points: transfer design §Q; verification mapping §P.
- Wrong answer: “They’d still learn something.”

**W7.4 — What if the student passes because of a hint?**
- Testing: metric gaming.
- Good answer: “Hinted passes gain half (+0.06 vs +0.12), hint dependence ≥0.50 suppresses
  transfer/challenge and boosts review, and transfer must still pass independently. Caveat: the demo
  slice has no hint endpoint yet, so `hint_used` is plumbed but always False on this path — say that.”
- Key points: damping + gates; honest gap.
- Wrong answer: “Hints don’t affect mastery.”

**W7.5 — What if the transfer problem is too easy?**
- Testing: validity critique.
- Good answer: “Fair risk: same-difficulty + bidirectional unsolvability cross-checks mitigate it,
  but difficulty parity is designer-judged, not psychometrically calibrated. Future: item analysis
  (pass rates, discrimination) per problem + adaptive difficulty. Current bank difficulties are 1–3
  only.”
- Key points: admit no IRT/calibration; propose measurement.
- Wrong answer: “Our transfers are proven equal.”

**W7.6 — What if your misconception taxonomy is wrong?**
- Testing: falsifiability.
- Good answer: “It’s a hypothesis encoded as data: centralized in one package so it’s cheap to
  revise; validator/belonging checks would catch ID drift; evidence refs + transfer outcomes provide
  the falsification signal (persistent SURFACE_FIX ⇒ wrong cause or wrong remediation). Version the
  taxonomy and track diagnosis→transfer precision per MID.”
- Key points: single source of truth = cheap revision; propose per-MID precision tracking.
- Wrong answer: “Experts wrote it, so it’s right.”

**W7.7 — Why should this be called adaptive learning?**
- Testing: definitional rigor.
- Good answer: “Because the next action is a computed function of the learner’s state
  (mastery/band, recurrency, trend, hints, transfers, prerequisites) through a published R1–R8
  policy — not a static sequence, not vibes. Modest scope (heuristic, single-track, C3-deep) but
  genuinely state-dependent and deterministic.”
- Key points: state-dependence + determinism = the claim; admit heuristic (not ML-based) adaptation.
- Wrong answer: “Because AI personalizes everything.”

**W7.8 — How is this different from a coding platform with AI feedback?**
- Testing: differentiation.
- Good answer: “Four things such platforms lack: (1) evidence-validated diagnosis with abstention,
  (2) a persistent learner model with recurrence math, (3) mandatory transfer + pair verification,
  (4) deterministic state-driven adaptation. AI feedback alone is step 1 of our 10-step loop.”
- Key points: §A.5 table.
- Wrong answer: feature-listing without the loop.

**W7.9 — What happens if your learner model becomes inaccurate?**
- Testing: error recovery.
- Good answer: “Every input is validated; every transition is event-logged with reasons so
  `explain_mastery` can audit it; improvement sweeps auto-clear stale flags; transfer verdicts
  continuously re-ground mastery in fresh performance. Structural risk remains (in-memory prototype
  loses state on restart) — durability is the fix, plus future per-MID calibration.”
- Key points: auditability + self-correction + honest persistence gap.
- Wrong answer: “The formula is correct so it can’t drift.”

**W7.10 — What are the current limitations of Cognify?**
- Testing: honesty under pressure (the most important answer).
- Good answer: deliver §AC from memory: C3-deep demo (rules/UI), read-only per-concept/history/
  catalog views (20B) over throwaway in-memory sessions, deterministic-mode LLM default, Java
  execution without track/UI/bank, no auth/dashboard/eval, no dedup, Docker-required,
  difficulty 1–3, hint plumbing without hint UI.
  End with: “The loop is real but narrow — our roadmap widens it without changing its shape.”
- Key points: never inflate; frame limits as scoped next steps (§AD).
- Wrong answer: hand-waving or claiming roadmap items as done.

---

## X — Endpoint questions

For each endpoint: why it exists, who calls it, what it receives/returns, validation, services
called, state modified, what can go wrong — plus a flow chart.

### X.1 `POST /student/sessions` (core-backend)

- Why: bootstrap a throwaway learning session and hand the client its first problem without leaking answers.
- Who calls: `SessionProvider.boot/startFresh` (web); tests.
- Receives: `{language_track?: "python"}` (extras ignored). Returns: `{session_id, language_track,
  journey_state, problem}` (canonical view).
- Validation: track normalized; non-`python` ⇒ 422. Unknown shapes ⇒ 422 via pydantic.
- Services called: problem-bank loader (canonical). No execution/AI/learner-write.
- State modified: new in-memory SQLite DB + user + journey + session dict entry.
- What can go wrong: bank file missing ⇒ 404/500-class; process restart wipes sessions (prototype).

### X.2 `GET /student/problems/{problem_id}` (core-backend)

- Why: (re)fetch the assigned problem’s safe view (e.g. after resume).
- Who calls: session enrich, practice init. Receives: path id + `?session_id`. Returns: `problem_view`.
- Validation: 404 unknown session; 404 bank miss; 422 role/language/journey mismatch.
- Services: loader only. State: none (read-only).
- What can go wrong: stale `session_id` (storage vs restart) ⇒ 404 ⇒ client starts fresh (by design).

### X.3 `POST /student/submissions` (core-backend — the exam question)

- Why: the entire learning loop behind one verb. Receives: `{session_id, problem_id, code}`.
  Returns: branch-dependent bundle (§E/F).
- Validation: session 404; empty/oversize code 422; problem 404/422; transfer-without-pass 409.
- Services called: execution-service (HTTP), evidence builder, diagnosis (rules/LLM/fallback),
  learner_engine, adaptive, verification, closed_loop — in branch order (§F.2).
- State modified: FAILED/error ⇒ 1 record; transfer ⇒ 0–2 records via closed loop; canonical pass ⇒
  stash only. Always commits (or noops safely).
- What can go wrong: exec-down 503; malformed exec reply 502; Docker-down 503; repeated submits
  append (no dedup); oversized code 422; spoof fields silently dropped.

### X.4 `GET /student/journey` (core-backend)

- Why: “what next” snapshot for Home/Learn/Progress without submitting. Receives: `?session_id`.
  Returns: ids + `journey_state{stage, canonical_passed, transfer_available, band, mastery_claim}` +
  `verification` + `recommendations`.
- Validation: 404 unknown session. Services: learner views + adaptive (read-only).
- State: none. What can go wrong: empty recommendations before any attempt (UI shows “No
  recommendation yet” — normal).

### X.5 `POST /diagnose` (ai-service)

- Why: stateless second opinion over one EvidencePack (also the integration seam if core-backend ever
  calls AI over HTTP instead of in-process).
- Who calls: operators/tests/pipeline helpers today; core-backend student slice uses the same logic
  via shared modules. Receives: `{evidence_pack}` (`extra=forbid`). Returns: `DiagnosisResult`
  (always 200 on valid pack).
- Validation: pack schema/taxonomy ⇒ 422 on malformed pack. Services: none downstream (pure + optional
  LLM egress). State: none.
- What can go wrong: no LLM configured ⇒ deterministic result (by design, not an error); malformed
  LLM JSON ⇒ fallback (still 200).

### X.6 `POST /execute` (execution-service)

- Why: the only door through which untrusted code enters. Receives: `{language, code, tests[1..50],
  timeout_seconds∈[1,30]}`. Returns: `ExecutionResult` with per-test detail + decisive pointers.
- Validation: language/code/tests/timeout ⇒ 422; Docker-down ⇒ 503.
- Services: Docker daemon (CLI). State: none durable (containers/volumes removed).
- What can go wrong: compile/runtime/timeout semantics per language (§G); Java double-compile cost;
  oversized payloads rejected before any container starts.

### Endpoint flow chart (one picture for the board)

```text
                    ┌──────────────┐
                    │ POST /student│
                    │  /submissions│
                    └──────┬───────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        canonical        canonical    transfer
         FAILED           PASSED      submit
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐  stash pass   ┌─────────┐
        │evidence→ │  unlock       │execute→ │
        │diagnose→ │  transfer     │verify→  │
        │record→   │               │closed-  │
        │intervene │               │loop→    │
        └────┬─────┘               │record×N │
             ▼                     └────┬────┘
        feedback+retry            verify+recs
```

---

## Y — File-level viva questions

One-to-three questions per important file, with short answers (file:line anchors are conceptual —
open the file and search the symbol).

**`learner_engine.py`** — Q: “Why is it separate from `adaptive/policy.py`?” A: writes vs reads —
engine mutates validated state and owns the formula call; policy only reads supplied numbers, so a
policy bug can never corrupt memory. Q: “Who may update mastery?” A: only this file’s
`record_attempt` (via repositories; AI/adaptive/verification cannot). Q: “What happens inside
`record_attempt`?” A: validate → prior-rate → `compute_mastery_update` → counters → recurring →
improvement sweep → append 3–5 events → return transition + views + flags.

**`closed_loop.py`** — Q: “What does `plan_records` buy us?” A: pure, DB-free 0/1/2-record mapping
(INCOMPLETE/NOT/SURFACE+VERIFIED) testable without a database. Q: “What does orchestration NOT own?”
A: everything (§P list) — it cues owners in order. Q: “Why is re-running non-idempotent?” A:
append-only events with no dedup key (honest prototype gap).

**`student.py`** — Q: “Where is the spoofing protection?” A: `extra="ignore"` models +
`_resolve_problem` server-side resolution + allowlist views; only code text is attacker-controlled.
Q: “Where are hidden tests protected?” A: `problem_view` allowlist + `to_student_view` redaction +
2000-char truncation + UI redaction + leak-grep tests. Q: “Why does canonical PASS not write
mastery?” A: the pass is stashed; mastery moves on FAILED/error immediately and on verification
outcomes via closed loop (PASS alone is not learning evidence).

**`execution_client.py`** — Q: “Why a separate HTTP client module?” A: single fail-closed contract
(503 vs 502), deep response validation, timeout formula — one place to get the boundary right.
Q: “What stops local-execution fallback?” A: design (no runner imports) + tests (`PWNED` probe,
`_default_runner_factory` raises).

**Docker sandbox (`sandbox.py`)** — Q: “Why a helper container?” A: service-in-Docker vs
daemon-outside ⇒ named volume staged by a throwaway container that only writes files. Q: “List the
containment flags.” A: `--rm, --network none, --memory 256m (+swap), --cpus 1.0, --pids-limit 128,
-v vol:/workspace, -w /workspace, -i image`, no env flags. Q: “Docker down?” A:
`SandboxUnavailableError` ⇒ 503; host execution refused by message and by construction.

**`mastery/formula.py`** — Q: “Recite the formula.” A: §L constants + branches + momentum +
clamp/round4; severities 0/0.5/0.75/0.75/1.0; bands 0.40/0.60/0.80. Q: “Why momentum?” A: rewards
consistency (±0.02 typical) without letting streaks dominate (bounded ±0.02). Q: “Prove a single
pass never masters.” A: 0.20+0.18 max = 0.38 < 0.40 novice ceiling… (even the best single delta
0.18 keeps a fresh learner in novice).

**`adaptive/policy.py`** — Q: “Recite R1–R8 in order.” A: §N tree. Q: “Why can urgency never promote
a tier?” A: bases are 10+ apart (…,70/80/100) while urgency caps at +10 — weaker concepts win
*within* a tier only. Q: “When is transfer emitted?” A: proficient+ AND ready-gate AND not blocked.

**`adaptive/ranking.py`** — Q: “Why a separate sort module?” A: policy assigns, ranking orders —
keeps priority arithmetic independently testable from ordering. Q: “State the key.” A:
`(-priority, concept, action, problem, reason_code, reason)`.

**`verification/engine.py`** — Q: “State the decision table.” A: §O six rows. Q: “Why does
transfer-PASS with retry-FAIL still give NOT_IMPROVED?” A: no retry evidence ⇒ nothing verified;
transfer alone is asserted-passing without a baseline. Q: “Does confidence matter?” A: never — only
PASS booleans; hint levels likewise ignored.

**Diagnosis `rules.py`** — Q: “Why must BOTH code shape and output signature match?” A: shape alone
could be coincidental; uniform dynamic signature (every failure −1, or −n) ties the shape to the
observed breakage. Q: “Why require ≥1 pass for R1 but not R2?” A: R1’s undercount-by-one needs a
passing control showing the loop *mostly* works; R2’s dropped-terminal-value signature is decisive
without one. Q: “What does abstention return?” A: `None` — the LLM/fallback chain takes over.

**`problem_schema/models.py`** — Q: “What makes a problem file valid?” A: §Q list (IDs, difficulty
1–5 int, role, ≥1 public, unique test IDs, ≥1 belonging MID…). Q: “Why bool-reject difficulty?” A:
`True == 1` in Python would silently pass range checks — strict `type(x) is int` prevents it.

**`api.ts` (frontend)** — Q: “How many backends does the UI call?” A: one (core-backend), four
functions. Q: “Where do raw taxonomy IDs leak?” A: nowhere by default — `stripCodes` rewrites them;
`?debug=1` only.

---

## Z — “If they ask me to draw on the board”

Ten hand-drawable diagrams (30–60 seconds each). Practice each once.

**1. High-level architecture (boxes + arrows):**
`[Browser] → [Core :8000] → [Exec :8002] → [Docker]` with `[Core] → [AI :8001]` (reasons),
`[Core] ↔ [Learner DB]`, and `[Mastery/Adaptive/Verify/Bank/Taxonomy]` as satellites of Core.
Label: “state / reasons / executes”.

**2. Student submission flow:** §F.2 vertical chain (browser → validate → resolve → execute →
branch → render). Mark 409/503/502 exits on the side.

**3. Execution flow:** `code+tests → compile? → per-test run → normalize → compare → aggregate
(TIMEOUT>RUNTIME>FAILED>PASSED) → decisive`. Write limits alongside (256m/1CPU/128/none/5s).

**4. Diagnosis flow:** `pack → rules? (0.70 HIT→done) → LLM? (validate+gate) → fallback (≤0.55)` with
`llm|fallback` sources. Write `MIN_CONF 0.50` on the gate.

**5. Learner model flow:** `record_attempt → validate → mastery → counters → recurring → improve →
events`. Circle “ONLY writer”.

**6. Mastery update flow:** `prev + (base ± momentum) → clamp → round4 → band`. Plug 0.20 −0.085 as
the worked arrow.

**7. Adaptive decision tree:** §N tree (prereq → band → recurring → readiness → modifiers). Write
thresholds (0.60/0.40/0.80), boosts (+15/+10), bases (100/80/70/50/40/30).

**8. Verification flow:** §O six-row table (missing/×, non-PASS, PASS+missing, PASS+non-PASS,
PASS+PASS). Underline PASS+PASS = VERIFIED_IMPROVED.

**9. Closed-loop flow:** §P mapping table (2/2/1/0 records) + `run_closed_loop` order
(verify → record → snapshot → recommend).

**10. Complete end-to-end:** §T condensed to one column of 10 boxes with the §A arrows; end with
“same evidence + same history ⇒ same everything (deterministic)”.

---

## AA — 5-minute explanation (speak this)

> Rehearse aloud once. Natural engineering-student voice, no marketing. ~700 words ≈ 5 minutes.

“So Cognify is a closed-loop programming tutor — the problem we saw is that beginners fail for
different underlying reasons, like off-by-one bounds versus misunderstanding Python’s range, but
normal platforms only say pass or fail. So students patch symptoms, nothing remembers what they got
wrong before, and nobody checks whether the fix actually generalized.

Architecture-wise there are four pieces. A Next.js frontend that just shows problems and results.
A core backend on port 8000 that orchestrates everything and is the only thing allowed to write
learner state. An AI service on 8001 that only reasons about one evidence pack at a time and can
never touch the database. And an execution service on 8002 that runs untrusted code inside Docker
sandboxes — no network, capped memory, CPU and PIDs, always cleaned up. Our rule is: the LLM
suggests, deterministic code disposes.

When a student submits, the browser sends only session, problem, and code. The backend re-resolves
the problem server-side — tests, concept, everything — so the client can’t spoof anything, and
hidden tests never leave the server. The code goes over HTTP to the execution service, runs
test-by-test in the sandbox, and comes back as a status: passed, failed, compile error, runtime
error, or timeout.

If it fails, we build what we call an EvidencePack — the code, the decisive failed test, expected
versus actual output, plus the student’s history on this concept. Diagnosis then happens in a fixed
order: first two exact rules for our C3 loops slice — for example, `range(len(nums)-1)` in the AST
plus every failed test undercounting by exactly one means off-by-one, confidence 0.70. If the rules
abstain, we can ask the LLM with a strict JSON contract, but its answer must survive validation —
right concept, candidate-only misconception ID, confidence above 0.5, refs that cite the failure —
or it’s thrown away. And if anything fails, a deterministic fallback picks the best history-informed
candidate. So there’s never silence, and never a hallucination that becomes truth.

That diagnosis goes into the learner model through one function, record_attempt. It recomputes
mastery with a fixed formula — fresh concepts start at 0.20, a clean pass gains 0.12, hints halve
gains, transfer adds 0.04, failures subtract by severity, timeouts worst at minus 0.12 — then
clamps and bands it into novice, emerging, proficient, mastered. It also bumps misconception
counters and checks recurrence: twice in the last five, thrice ever, or twice across problem
variants means recurring, which escalates teaching from a nudge up to reteach. Three clean passes
clear it.

The intervention the student sees is built deterministically from that: a level from history, L1
to L4, plus a type tied to the misconception — boundary-check for off-by-one, trace-the-loop for
range exclusivity — with the decisive test quoted. The student retries the same problem. Only a
pass unlocks the transfer problem: same skill and misconceptions, same isomorphic group, but a new
story — counting cold days instead of divisible numbers — cross-checked so you can’t copy the old
answer over.

Then verification compares the pair: pass plus pass is verified-improved; pass plus fail is a
surface fix, meaning they patched the instance without repairing the mental model; a failed retry
is not improved; anything missing is incomplete and writes nothing. The closed loop records one or
two attempts accordingly and calls the adaptive engine, which is eight deterministic rules:
prerequisites first, then band — review and remedial when novice, practice when emerging,
practice plus transfer when proficient, challenge when mastered — with recurring, declining trend,
and hint dependence adjusting priority and suppressing harder steps until earned.

So the result is: every failure becomes evidence, every intervention cites it, every claim of
improvement must survive transfer, and everything is remembered and ranked deterministically.
Right now the full loop is real but narrow — Python C3 deep, 24 problems across C1 to C8 in the
bank, deterministic mode by default — and our roadmap widens it: durable database, history
endpoints, Java track, auth, and proper evaluation. The loop’s shape doesn’t change; it just gets
wider and production-hard.”

---

## AB — 30-second explanation

> For: “What is Cognify?”

“Cognify is a closed-loop programming tutor: it runs your code in a Docker sandbox, diagnoses WHY
it failed from observed evidence — not guesses — teaches that specific misconception, makes you
prove the fix on a new transfer problem, and deterministically adapts what comes next from a
learner model that remembers everything. Passing once isn’t enough; transfer is the proof.”

---

## AC — Current implementation status (honest table)

Evidence/file column lets a reviewer verify each row in under a minute.

| Feature | Status | Evidence / File | Notes |
|---|---|---|---|
| Problem bank (24 Python, C1–C8 × canonical/remedial/transfer, 2+3 tests each) | `[IMPLEMENTED]` | `problem-bank/python/*.json` (24), `packages/problem_bank/tests/test_step19.py` | Difficulties 1–3 only; `problem-bank/java/` absent. |
| Code execution (Python, Docker sandbox, 5 statuses) | `[IMPLEMENTED]` | `services/execution-service/app/*.py`, `GET /languages`, `POST /execute` | Limits §G.2; fail-closed 503. |
| Java execution | `[PARTIALLY IMPLEMENTED]` | `java_runner.py` (works; double-compile inefficiency), `GET /languages` lists java | No track/UI/bank/rules for Java. |
| Deterministic C3 diagnosis (2 rules, 0.70) | `[IMPLEMENTED]` | `services/ai-service/app/rules.py`, `tests/test_step15.py` | C3-only; others fall to LLM/fallback. |
| LLM diagnosis path | `[PARTIALLY IMPLEMENTED]` | `llm_client/prompt/validator/gate/service.py`, `POST /diagnose` | Exists + tested; default env disables (`LLM_PROVIDER=` empty). |
| Fallback classifier + gate + validator | `[IMPLEMENTED]` | `fallback/gate/validator.py` + tests | Caps 0.55/0.40; gate 0.50 + grounding. |
| Interventions L1–L4 + curated types | `[IMPLEMENTED]` | `interventions.py`, `student.INTERVENTION_COPY` | History-derived levels; C3-curated, generic `TARGETED_HINT` otherwise. |
| Learner model (tables, counters, flags, events) | `[IMPLEMENTED]` | `core-backend/app/{models,repositories,learner_engine}.py` | 6 tables; write-owner enforced. |
| Persistence | `[PARTIALLY IMPLEMENTED]` | `db.py` (file SQLite default) vs `StudentStore` (per-session `:memory:`) | Prototype loses sessions on restart; `DATABASE_URL` reserved. |
| Mastery formula + bands + trend | `[IMPLEMENTED]` | `packages/mastery/formula.py`, `tests/test_mastery.py` | Constants §L; single pass never masters. |
| Recurring detection R1/R2/R3 + improvement | `[IMPLEMENTED]` | `packages/mastery/weakness.py` + engine sweep | Thresholds 2-in-5 / 3-ever / 2-variants / 3-clean. |
| Adaptive engine R1–R8 + ranking | `[IMPLEMENTED]` | `packages/adaptive/*.py` + tests | Thresholds/gates §N. |
| Verification (4 outcomes, decision table) | `[IMPLEMENTED]` | `packages/verification/*.py` + tests | PASS+PASS ⇒ verified; mastery disclaimed. |
| Closed loop orchestration | `[IMPLEMENTED]` | `closed_loop.py` + `test_closed_loop.py` | 2/2/1/0 mapping; non-idempotent (no dedup). |
| Student API (7 endpoints + health) | `[IMPLEMENTED]` | `student.py`, `main.py`, flow + read tests | Spoof/hidden/CORS/503/502/409 handling; 20B views add MID/iso/mastery-float redaction. |
| AI/Exec APIs + health | `[IMPLEMENTED]` | `ai-service/app/main.py`, `execution-service/app/main.py` | 2 + 3 endpoints. |
| Frontend (Home/Learn/Practice/Progress/History) | `[IMPLEMENTED]` (C3-live; read views live) | `apps/web/src/**` + vitest (40 tests) | Live concept/history data; Practice C3-scoped; no auth. |
| Python track end-to-end | `[IMPLEMENTED]` | smoke + journey tests (`VERIFIED_IMPROVED` golden path) | C3 slice proven. |
| Authentication / users / JWT enforcement | `[PLANNED / NOT IMPLEMENTED]` | `JWT_*` env scaffold only; session.tsx disclaimer | Anyone can create sessions. |
| Persistent database (Postgres/migrations) | `[PLANNED / NOT IMPLEMENTED]` | `DATABASE_URL` placeholder (asyncpg URL vs sync engine mismatch noted) | No migrations; file-SQLite default unused by slice. |
| Per-concept / history / catalog read views (Step 20B) | `[IMPLEMENTED]` | `student.py` read-only `GET`s + `test_student_read.py` (21 tests) | Concepts/history/problems served; no writes. |
| Instructor dashboard | `[PLANNED / NOT IMPLEMENTED]` | Nothing in repo | Data exists; UI doesn’t. |
| Evaluation / benchmarking (learning gains) | `[PLANNED / NOT IMPLEMENTED]` | No study/suite in repo | Mechanism exists; efficacy unmeasured. |
| Stronger isolation (gVisor/Firecracker/K8s) | `[PLANNED / NOT IMPLEMENTED]` | Nothing in repo | Docker flags are the boundary. |
| `infra/` , root `tests/`, `docs/` (pre-handbook) | Empty / reserved | Verified 2026-09-20 | Compose + Dockerfile cover current ops. |

---

## AD — Future steps (separate from current architecture)

> Only steps grounded in the repository/project state (empty dirs, scaffold
> envs, honest gaps found above). All marked NOT IMPLEMENTED YET where applicable.

### CURRENT (done — do not re-plan)

Steps 0–20B: taxonomy → problem schema → execution → evidence → LLM config → learner tables →
adaptive → verification → closed loop → bank loader/pipeline → transfer design → journey → C3
diagnosis rules → student slice → smoke hardening → learner-intelligence upgrade → C1–C8 bank
expansion (24) → 20A product foundation (Home/Learn/Practice/Progress/History on existing APIs) +
Docker sandbox architecture fix → 20B read-only student data APIs (`GET /student/concepts`,
`GET /student/history`, `GET /student/problems`) lighting up Learn/Progress/History/Home with
real learner state (no algorithm changes). The C3 loop is fully green in tests.

### NEXT (known planned work — NOT IMPLEMENTED YET)

1. **Durable persistence** (NOT IMPLEMENTED YET): shared engine via `DATABASE_URL` (fix asyncpg→sync
   driver), migration tooling, session table replacing per-session `:memory:` DBs.
2. **Java track surfacing** (NOT IMPLEMENTED YET): `problem-bank/java/`, track-aware resolution + UI
   switcher, Java diagnosis rules; fix `java_runner` double-compile first.
3. **AuthN/AuthZ** (NOT IMPLEMENTED YET): real identities bound to `users`, scoped queries, session
   expiry/revocation (`JWT_*` currently scaffold); move the Step-20B read views behind auth.
4. **Submission dedup / idempotency keys** (NOT IMPLEMENTED YET): stop append-on-retry for identical
   resubmits and closed-loop re-runs.
5. **Hint system end-to-end** (NOT IMPLEMENTED YET): hint endpoint + UI wired to the already-plumbed
   `hint_used`/`hint_count` path (formula + R8 already honor it).
6. **Evaluation suite** (NOT IMPLEMENTED YET): per-MID diagnosis→transfer precision, recurrence
   clearance rates, mastery trajectories, transfer difficulty parity analysis.

### FUTURE PRODUCTIZATION (directional — NOT IMPLEMENTED YET)

Postgres + Redis + queue-backed execution replicas; AI response caching (pack-hash) + budgets;
per-user quotas/rate limits; instructor read-only analytics over existing tables; item calibration
(difficulties beyond 1–3); multi-classroom tenancy; observability (structured logs/metrics/traces);
production ops for `infra/` (currently empty). None of this changes the loop’s shape —
execute → evidence → diagnose → intervene → retry → transfer → verify → remember → adapt.

---

## Final self-check (author’s verification log)

Completed 2026-09-20 against the live repo (no app files modified; `git status` untouched by design):

1. ✅ Every major component covered (frontend, 3 services, 7 packages, bank, taxonomy).
2. ✅ Every implemented backend endpoint covered (§F: 7 + 2 + 3 + healths; planned separated).
3. ✅ Learner model explained (§K: tables, views, writers, events, track isolation).
4. ✅ Mastery formula from actual code (§L: constants/bands/severity/momentum verbatim + example).
5. ✅ Adaptive rules from actual code (§N: R1–R8 order, thresholds, priorities, gates).
6. ✅ Diagnosis rules explained (§I: 2 C3 rules with triggers/evidence/MID/confidence/intervention).
7. ✅ Evidence pack explained (§H: 8 rows + builder behavior + secret hygiene).
8. ✅ Verification explained (§O: 4 outcomes + 6-row table + PASS≠VERIFIED_IMPROVED).
9. ✅ Execution sandbox explained (§G: path, limits, helper, fail-closed, Python vs Java).
10. ✅ Problem bank explained (§Q: schema, roles, groups, 24-problem inventory, transfer design).
11. ✅ Frontend explained (§R: routes, session, practice flow, rendering, gaps marked).
12. ✅ Security explained (§S: 13 implemented + 3 marked planned/partial, WHAT/WHY/HOW).
13. ✅ End-to-end flow explained (§E: 21 steps with I→P→O→N; §T diagram).
14. ✅ File responsibilities explained (§D: every important source file + spotlight on `record_attempt`).
15. ✅ Company-style questions included (§W: 7 levels, 40 questions, all with testing/answer/keys/wrong).
16. ✅ Endpoint questions included (§X: 6 endpoints + chart).
17. ✅ File-level questions included (§Y: 12 file groups).
18. ✅ Board-drawing diagrams included (§Z: 10 practice diagrams).
19. ✅ Current vs planned separated (§AC table + §AD CURRENT/NEXT/FUTURE; labels throughout).
20. ✅ No unsupported claims as facts (gVisor/K8s/auth/DB/eval-metrics explicitly marked absent;
    inferences labeled; Java/LLM-dormancy/hint-gap stated).

**Report:** document created at `docs/COGNIFY_INTERNAL_WORKING_AND_VIVA_HANDBOOK.md`; ~40 source
files plus README/compose/Dockerfile/envs inspected directly; ~120 more via 5 parallel code-reading
passes with quoted evidence; major areas all covered. Areas with thin evidence: `infra/` and root
`tests/` (empty — noted, not filled in); HTTP AI-service usage from the student hot path
(in-process alias-load observed instead — marked as inferred); production scaling/auth (absent —
marked planned). **No application files were modified** (handbook only; no commit/push).

<!--HANDBOOK-END-->








