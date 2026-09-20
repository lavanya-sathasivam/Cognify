/** Learn / Progress / History page tests (Step 20B).
 *
 * All three pages render REAL backend state now: Learn and Progress from
 * GET /student/concepts (eight concepts, honest not-started states),
 * History from GET /student/history (populated or honestly empty).
 * Level labels, never raw numbers; human language, never internal codes.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { SessionProvider } from "../../components/session";
import LearnPage from "../learn/page";
import ProgressPage from "../progress/page";
import HistoryPage from "../history/page";

const PROBLEM = {
  problem_id: "PY-C3-COUNT-DIV",
  language: "python",
  concept_id: "C3",
  title: "Count Divisible Numbers",
  statement: "Count how many numbers are divisible by k.",
  constraints: ["1 <= n <= 1000"],
  input_format: "n and k, then n integers.",
  output_format: "A single integer.",
  starter_code: "def count_divisible(nums, k):\n    raise NotImplementedError\n",
  difficulty: 2,
};

const TITLES: Record<string, string> = {
  C1: "Variables, Types, Operators, I/O",
  C2: "Conditionals & Boolean Logic",
  C3: "Loops & Iteration Control",
  C4: "Functions / Methods, Parameters, Scope & Return",
  C5: "Lists / Arrays & Strings",
  C6: "Dictionaries / Maps, Sets & Nested Structures",
  C7: "OOP: Classes, Objects, Encapsulation, Inheritance",
  C8: "Recursion, Exceptions & Algorithmic Complexity Basics",
};

const GROUPS: Record<string, string> = {
  C1: "Foundations",
  C2: "Control Flow",
  C3: "Control Flow",
  C4: "Functions",
  C5: "Collections",
  C6: "Collections",
  C7: "Objects",
  C8: "Recursion & Beyond",
};

const PREREQS: Record<string, string[]> = {
  C1: [],
  C2: ["C1"],
  C3: ["C1", "C2"],
  C4: ["C1", "C2", "C3"],
  C5: ["C1", "C3", "C4"],
  C6: ["C1", "C3", "C5"],
  C7: ["C1", "C4", "C5"],
  C8: ["C2", "C3", "C4", "C7"],
};

function conceptCard(id: string, overrides: Record<string, unknown> = {}) {
  return {
    concept_id: id,
    title: TITLES[id],
    description: `${TITLES[id]} scope.`,
    group: GROUPS[id],
    prerequisites: PREREQS[id],
    status: "not_started",
    band: "novice",
    mastery_claim: false,
    trend: "unknown",
    attempt_count: 0,
    pass_count: 0,
    fail_count: 0,
    transfer: { attempts: 0, successes: 0, failures: 0, success_rate: 0 },
    hint_dependence: 0,
    hint_count: 0,
    recent_history: [],
    active_misconception_count: 0,
    ...overrides,
  };
}

const C3_STARTED = {
  status: "started",
  band: "emerging",
  trend: "stable",
  attempt_count: 2,
  pass_count: 1,
  fail_count: 1,
  recent_history: [
    { problem_id: "PY-C3-COUNT-DIV", passed: false, is_transfer: false, hint_used: false },
    { problem_id: "PY-C3-COUNT-DIV", passed: true, is_transfer: false, hint_used: false },
  ],
  active_misconception_count: 0,
};

function conceptsPayload(c3: Record<string, unknown> = C3_STARTED) {
  return {
    session_id: "sess-pages",
    language_track: "python",
    concepts: ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"].map((id) =>
      conceptCard(id, id === "C3" ? c3 : {}),
    ),
    next_action: {
      action: "PRACTICE_PROBLEM",
      reason: "Keep practicing to make the idea stick.",
      problem_id: null,
      problem_title: null,
      concept_id: "C3",
    },
  };
}

function historyPayload() {
  return {
    session_id: "sess-pages",
    total: 2,
    limit: 20,
    items: [
      {
        order: 1,
        created_at: "2026-09-20T10:00:00",
        problem_id: "PY-C3-COUNT-DIV",
        problem_title: "Count Divisible Numbers",
        concept_id: "C3",
        concept_title: "Loops & Iteration Control",
        outcome: "failed",
        execution_status: "FAILED",
        is_transfer: false,
        feedback: "Loop bounds identified — review the feedback and retry.",
        verified: false,
      },
      {
        order: 2,
        created_at: "2026-09-20T10:05:00",
        problem_id: "PY-C3-COUNT-DIV",
        problem_title: "Count Divisible Numbers",
        concept_id: "C3",
        concept_title: "Loops & Iteration Control",
        outcome: "passed",
        execution_status: "PASSED",
        is_transfer: false,
        feedback: "Solved correctly.",
        verified: false,
      },
    ],
  };
}

function sessionPayload(band = "emerging") {
  return {
    session_id: "sess-pages",
    language_track: "python",
    journey_state: {
      stage: "practicing",
      canonical_passed: false,
      transfer_available: false,
      band,
      mastery_claim: false,
    },
    problem: PROBLEM,
  };
}

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const key = `${method} ${String(url).replace(/^https?:\/\/[^/]+/, "")}`;
    if (!(key in routes)) throw new Error(`unexpected request: ${key}`);
    const body = routes[key];
    if (body instanceof Error) throw body;
    return { ok: true, status: 200, json: async () => body };
  });
}

function conceptRoutes() {
  return {
    "POST /student/sessions": sessionPayload(),
    "GET /student/concepts?session_id=sess-pages": conceptsPayload(),
  };
}

beforeEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

test("learn roadmap lists all eight concepts with honest states", async () => {
  vi.stubGlobal("fetch", mockFetch(conceptRoutes()));
  render(
    <SessionProvider>
      <LearnPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Learn Python")).toBeDefined();
  // Student UI shows human-readable titles, never raw concept ids.
  for (const id of ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]) {
    expect(await screen.findByText(TITLES[id])).toBeDefined();
  }
  expect(screen.queryByText(/C1 ·|C2 ·|C3 ·/)).toBeNull();
  // Backend groups structure the roadmap.
  expect(await screen.findByText("Foundations")).toBeDefined();
  expect(await screen.findByText("Recursion & Beyond")).toBeDefined();
  // Live C3 state uses a level label; everything else is honestly pending.
  expect(await screen.findByText("Developing")).toBeDefined();
  expect(screen.getAllByText(/Not started yet/).length).toBeGreaterThanOrEqual(7);
  // No fabricated gamification or locks ("expressions" contains "xp",
  // hence word boundaries).
  expect(screen.queryByText(/\bXP\b|\bstreak\b|\blocked\b|\bbadge/i)).toBeNull();
  // No internal codes leak into student UI.
  expect(screen.queryByText(/C[1-8]-M\d{2}/)).toBeNull();
});

test("learn shows an error state when concepts fail to load", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({ "POST /student/sessions": sessionPayload() }),
  );
  render(
    <SessionProvider>
      <LearnPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Couldn't load the roadmap.")).toBeDefined();
});

test("progress shows real levels, transfer, hints, and recommendation", async () => {
  vi.stubGlobal("fetch", mockFetch(conceptRoutes()));
  render(
    <SessionProvider>
      <ProgressPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Your progress")).toBeDefined();
  expect(await screen.findByText("Developing")).toBeDefined();
  // Current level is distinguished from mastery.
  expect(await screen.findByText("Not yet mastered — keep practicing")).toBeDefined();
  expect(await screen.findByText("Steady")).toBeDefined();
  expect(await screen.findByText(/2 attempts · 1 solved/)).toBeDefined();
  expect(await screen.findByText(/1 to retry/)).toBeDefined();
  expect(await screen.findByText(/No transfer attempts yet/)).toBeDefined();
  expect(await screen.findByText(/Working independently/)).toBeDefined();
  // Adaptive recommendation in student language.
  expect(
    await screen.findByText("Keep practicing this concept to make it stick."),
  ).toBeDefined();
  expect(screen.queryByText(/Mastery =|0\.\d+/)).toBeNull();
  expect(screen.queryByText(/C[1-8]-M\d{2}/)).toBeNull();
  expect(screen.getAllByText(/Not started yet/).length).toBe(7);
});

test("progress is honestly empty before any attempt", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/concepts?session_id=sess-pages": {
        ...conceptsPayload(),
        concepts: ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"].map((id) =>
          conceptCard(id),
        ),
      },
    }),
  );
  render(
    <SessionProvider>
      <ProgressPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("No progress yet")).toBeDefined();
});

test("progress shows an error state when concepts fail to load", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({ "POST /student/sessions": sessionPayload() }),
  );
  render(
    <SessionProvider>
      <ProgressPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Couldn't load your progress.")).toBeDefined();
});

test("history shows real attempts in human language", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/history?session_id=sess-pages&limit=20": historyPayload(),
    }),
  );
  render(
    <SessionProvider>
      <HistoryPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Your history")).toBeDefined();
  expect(
    (await screen.findAllByText("Count Divisible Numbers", { exact: false }))
      .length,
  ).toBe(2);
  expect(await screen.findByText("Needs another attempt")).toBeDefined();
  expect(await screen.findByText("Solved")).toBeDefined();
  expect(
    await screen.findByText(/Loop bounds identified/),
  ).toBeDefined();
  expect(screen.queryByText(/C[1-8]-M\d{2}/)).toBeNull();
  expect(screen.queryByText(/FAILED|PASSED/)).toBeNull();
});

test("history is honestly empty without attempts", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/history?session_id=sess-pages&limit=20": {
        session_id: "sess-pages",
        total: 0,
        limit: 20,
        items: [],
      },
    }),
  );
  render(
    <SessionProvider>
      <HistoryPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("No learning history yet")).toBeDefined();
});

test("history shows an error state when history fails to load", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({ "POST /student/sessions": sessionPayload() }),
  );
  render(
    <SessionProvider>
      <HistoryPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Couldn't load your history.")).toBeDefined();
});

test("learn highlights the recommended concept and prerequisites", async () => {
  vi.stubGlobal("fetch", mockFetch(conceptRoutes()));
  render(
    <SessionProvider>
      <LearnPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Recommended next")).toBeDefined();
  expect((await screen.findAllByText(/Builds on:/)).length).toBe(7);
});

test("history shows attempt order and execution results without raw codes", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/history?session_id=sess-pages&limit=20": historyPayload(),
    }),
  );
  render(
    <SessionProvider>
      <HistoryPage />
    </SessionProvider>,
  );
  expect(await screen.findByText(/Attempt 1/)).toBeDefined();
  expect(await screen.findByText(/Some tests failed/)).toBeDefined();
  expect(await screen.findByText(/All tests passed/)).toBeDefined();
  expect(screen.queryByText("FAILED")).toBeNull();
  expect(screen.queryByText("PASSED")).toBeNull();
});
