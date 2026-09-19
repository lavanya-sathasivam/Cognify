# COGNIFY

**COGNIFY** is an AI-powered adaptive programming learning system that understands **WHY** a student struggles with programming concepts, provides targeted interventions based on the student's diagnosed weaknesses and learning history, and verifies whether the student actually improved.

> Scaffold status: project structure + service health stubs only. No business logic implemented yet (no AI diagnosis, mastery, adaptive learning, code execution, or database models).

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
│   └── web/                  # Next.js + TypeScript + Tailwind (frontend)
├── services/
│   ├── core-backend/         # FastAPI — product API + learning-loop orchestration (later)
│   ├── ai-service/           # FastAPI — diagnosis / hints via LLM (later)
│   └── execution-service/    # FastAPI — sandboxed code execution (later)
├── packages/
│   ├── taxonomy/             # Shared error taxonomy (later)
│   ├── mastery/              # Shared mastery formula (later)
│   └── problem-schema/       # Shared problem JSON schemas (later)
├── problem-bank/
│   ├── python/               # Python problems + tests (later)
│   └── java/                 # Java problems + tests (later)
├── tests/                    # Cross-service test suites (later)
├── docs/                     # Architecture / API notes (later)
├── infra/                    # Deploy manifests (later)
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

### 5. Run everything with Docker (alternative)

```powershell
copy .env.example .env
docker compose up --build
```

Then open `http://localhost:3000` and the three `/health` endpoints above.

## Scope Note

This scaffold intentionally contains **no** Cognify business logic yet:

- No AI diagnosis / hints
- No mastery calculation / learner model
- No adaptive roadmap / policy
- No code execution / test evaluation
- No database models / migrations

## Sub-projects (no separate READMEs)

This repo keeps a **single `README.md` + single `requirements.txt` + single `Dockerfile`** at the root.
What the old per-folder READMEs said:

- `apps/web/` — Next.js frontend. `npm install`, `npm run dev`, edit `app/page.tsx`. See Next.js docs for details.
- `packages/taxonomy/` — Shared error taxonomy placeholder, logic added later.
- `packages/mastery/` — Shared mastery formula placeholder, logic added later.
- `packages/problem-schema/` — Shared problem JSON schemas placeholder, logic added later.
- `problem-bank/python/` — Python problems + tests placeholder, content added later.
- `problem-bank/java/` — Java problems + tests placeholder, content added later.
- `docs/` — Architecture / API notes placeholder, added later.
- `infra/` — Deploy manifests placeholder, added later.
- `tests/` — Cross-service test suites placeholder, added later.

## Docker Note

Single shared `Dockerfile` at root builds all 3 Python services via build args:

- `SERVICE_NAME`: `core-backend` | `ai-service` | `execution-service`
- `SERVICE_PORT`: `8000` | `8001` | `8002`

`docker-compose.yml` passes the right args per service. No per-service Dockerfiles needed
unless a service later needs divergent system deps — then split again.
