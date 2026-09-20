# COGNIFY

**COGNIFY** is an AI-powered adaptive programming learning system that understands **WHY** a student struggles with programming concepts, provides targeted interventions based on the student's diagnosed weaknesses and learning history, and verifies whether the student actually improved.

> Prototype status: the full learning loop works for the Python C3 slice
> (execution → Evidence Pack → diagnosis → learner model → intervention →
> retry → transfer → verification → adaptive recommendation) with a
> student-facing API and UI. See [Current prototype limitations](#current-prototype-limitations).

## Core Workflow

The core learning loop:

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

Key mechanism:

```
FAILURE → DIAGNOSIS → TARGETED INTERVENTION → RETRY
→ TRANSFER / RELATED PROBLEM → VERIFICATION → LEARNER MODEL UPDATE
```

The system distinguishes between an isolated coding mistake, an implementation mistake, a recurring misconception, a concept-level weakness, and improvement after intervention.

## Language Tracks

The student chooses **ONE** programming language for their learning journey:

- **Python**
- **Java**

All learning state (roadmap, mastery, history) is namespaced per `(user, language_track)`.

## 8 Learning Concepts

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

## Project Structure

```text
Cognify/
├── apps/
│   └── web/                  # Next.js + TypeScript + Tailwind student UI (Step 16)
├── services/
│   ├── core-backend/         # FastAPI — product API + student slice + learner model (Steps 8, 11, 16)
│   ├── ai-service/           # FastAPI — diagnosis / rules / interventions (Steps 7, 15)
│   └── execution-service/    # FastAPI — sandboxed code execution (Step 5)
├── packages/
│   ├── taxonomy/             # Shared error taxonomy (Step 2)
│   ├── mastery/              # Shared mastery formula + weakness rules (Step 8)
│   ├── problem-schema/       # Shared problem JSON schemas (Step 4)
│   ├── evidence/             # EvidencePack builder (Step 6)
│   ├── adaptive/             # Adaptive policy + ranking (Step 9)
│   ├── verification/         # Verification engine (Step 10)
│   └── problem_bank/         # Problem loader + execution/diagnosis pipeline + journey (Steps 12-14)
├── problem-bank/
│   ├── python/               # Python problems + tests (Steps 12-13)
│   └── java/                 # Java problems (reserved; UI does not expose Java yet)
├── tests/                    # Cross-service test suites (reserved)
├── docs/                     # Architecture / API notes (reserved)
├── infra/                    # Deploy manifests (reserved)
├── .venv/                    # Root Python virtual environment (local only, git-ignored)
├── .gitignore
├── .env.example              # Root env template (copy to .env)
├── Dockerfile                # Single shared image for all 3 Python services
├── requirements.txt          # Single shared Python deps for all services
├── docker-compose.yml        # Local orchestration for web + 3 services
└── README.md                 # Single project README (only one in repo)
```

Service ports (local defaults):

| Service | Port | Health |
|---------|------|--------|
| core-backend | 8000 | `GET http://localhost:8000/health` |
| ai-service | 8001 | `GET http://localhost:8001/health` |
| execution-service | 8002 | `GET http://localhost:8002/health` |
| web | 3000 | `http://localhost:3000` |

## Setup / Run Commands

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

> Note: live code execution shells out to the `docker` CLI, so the host
> running a backend (local or in compose) needs a working Docker daemon.
> Without it, execution-dependent endpoints fail closed (503) instead of
> running student code anywhere unsafe.

## Architecture overview

One request flows through the existing components; the student API only
orchestrates them:

```
student code
  → execution-service (sandboxed run + test evaluation, Step 5)
  → Evidence Pack (observed facts only, Step 6)
  → diagnosis: deterministic C3 rules → LLM (if configured) → fallback (Steps 7, 15)
  → learner model: record attempt + mastery (Step 8)
  → intervention: structured Step 15 object rendered by the UI (no invented advice)
  → retry → transfer problem
  → verification engine (Step 10) → closed loop writes + ranking (Step 11)
  → adaptive engine recommendation (Step 9)
```

Student API (core-backend, all JSON):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/student/sessions` | Start a session; returns the canonical problem (`PY-C3-COUNT-DIV`) |
| GET | `/student/problems/{id}` | Safe problem metadata (never any expected outputs) |
| POST | `/student/submissions` | Submit code for canonical (incl. retry) or transfer; runs the loop above |
| GET | `/student/journey` | Stage, verification, recommendations |

## Environment variables

Only these are read by the current application (everything else in the
`.env.example` files is reserved for later steps):

| Variable | Used by | Required? | Effect |
|----------|---------|-----------|--------|
| `STUDENT_CORS_ORIGINS` | core-backend | No (defaults to `http://localhost:3000`) | Browser origins allowed to call the API |
| `NEXT_PUBLIC_CORE_BACKEND_URL` | web | No (defaults to `http://localhost:8000`) | Backend URL baked into the frontend at dev/build time |
| `LLM_PROVIDER` (`""`/`openai`/`mock`) | ai-service | No (empty = deterministic rules + fallback mode) | Enables LLM diagnosis when set with a key |
| `LLM_API_KEY` | ai-service | Only with `LLM_PROVIDER=openai` | Secret; never leaves the backend |
| `LLM_MODEL` / `LLM_BASE_URL` / `LLM_TIMEOUT_SECONDS` | ai-service | No (safe defaults) | Model routing / endpoint / timeout |
| `DATABASE_URL` | core-backend | No (defaults to local SQLite file) | Prototype persistence; leave unset for the demo |
| `PORT`, `*_PORT`, `*_URL` | compose/services | Only under Docker | Wiring between containers |

LLM modes: **configured** (`LLM_PROVIDER=openai` + key → model diagnosis with
strict validation and fallback on any failure) vs **deterministic**
(default empty provider → Step 15 evidence rules, then the safe fallback
classifier). Student sessions work identically in both; no secrets are
ever exposed to the frontend.

## Running tests

From the repo root (venv activated):

```powershell
# Backend suites (Steps 5-15 + Step 16/17 API + smoke)
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
npm test        # vitest: UI states (render/submit/fail/retry/transfer/verified/errors)
npx tsc --noEmit  # type checking
npm run lint    # eslint
npm run build   # production build
```

## Demo walkthrough (3–5 minutes)

Prerequisites: backend on `:8000`, frontend on `:3000`, Docker daemon
available for live execution.

| Step | Do | What you see | Responsible component |
|------|----|--------------|----------------------|
| 1 | Open `http://localhost:3000` | Cognify header, Python track | web UI |
| 2 | Read the problem | “Count Divisible Numbers” (C3) | problem bank via student API |
| 3 | Paste the buggy loop (`for i in range(len(nums) - 1): …`) and Submit | — | execution-service (sandboxed) |
| 4 | Read the result | FAILED, why it failed, failing-test evidence, “Check whether your loop processes the final required element.” | Evidence Pack → diagnosis (Step 15 rule) → intervention |
| 5 | Fix the loop to visit every element, Submit again | — | same pipeline, retry path |
| 6 | Read the result | “Good improvement”, Continue button | student API (transfer unlocked) |
| 7 | Continue | “Count Cold Days” (shown as a related challenge, not as an isomorphic variant) | problem bank |
| 8 | Submit a correct transfer solution | — | execution-service |
| 9 | Read the result | VERIFIED_IMPROVED (“You solved the original problem and applied the idea…”) | verification engine + closed loop |
| 10 | Read the next step | Recommended action + reason (+ problem title when available) | adaptive engine |

Buggy starter for step 3 (fails 3 of 5 tests, decisive `P2`):

```python
def count_divisible(nums, k):
    count = 0
    for i in range(len(nums) - 1):
        if nums[i] % k == 0:
            count += 1
    return count
```

## Current prototype limitations

Honest boundaries for reviewers:

- Student persistence is **process-local/in-memory** (one SQLite DB per
  session); restarting the backend loses sessions.
- Deterministic diagnosis rules cover **selected C3/Python patterns**
  only; everything else uses the LLM (if configured) or the safe fallback.
- The **Java track is not exposed** in the UI (bank placeholder only).
- The **problem bank is small** (C3 canonical + transfer + probe).
- The UI never claims mastery unless the learner model reports band
  `mastered`.
- Re-submitting a transfer re-records attempts (append-only learner log,
  no dedup).
- Production would need durable persistence, auth, and stronger
  sandbox/deployment infrastructure — none of that is in this prototype.

## Scope Note

This prototype intentionally does **not** include:

- Authentication / payments
- Teacher or analytics dashboards
- Gamification or chat interfaces
- Java UI or AI problem generation
- New LLM providers, RAG, or vector databases
- Production cloud infrastructure
