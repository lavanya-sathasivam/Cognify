/** Home + navigation tests (Step 20A).
 *
 * Home renders only from existing endpoints (session + journey). No other
 * concept's progress is fabricated: only the live C3 journey appears.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { SiteHeader } from "../../components/layout";
import { SessionProvider } from "../../components/session";
import HomePage from "../page";

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

function sessionPayload() {
  return {
    session_id: "sess-home",
    language_track: "python",
    journey_state: {
      stage: "practicing",
      canonical_passed: false,
      transfer_available: false,
      band: "emerging",
      mastery_claim: false,
    },
    problem: PROBLEM,
  };
}

function journeyPayload() {
  return {
    session_id: "sess-home",
    language_track: "python",
    canonical_problem_id: "PY-C3-COUNT-DIV",
    transfer_problem_id: "PY-C3-COUNT-DIV-TRANSFER",
    journey_state: {
      stage: "practicing",
      canonical_passed: false,
      transfer_available: false,
      band: "emerging",
      mastery_claim: false,
    },
    verification: null,
    recommendations: [
      {
        action: "REMEDIAL_PROBLEM",
        reason: "Recurring weakness C3-M01 in C3 (2 recent, 3 total): remedial practice.",
        problem_id: null,
        problem_title: null,
      },
    ],
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

function conceptsPayload() {
  const card = (id: string, title: string, group: string) => ({
    concept_id: id,
    title,
    description: `${title} scope.`,
    group,
    prerequisites: [],
    status: id === "C3" ? "started" : "not_started",
    band: id === "C3" ? "emerging" : "novice",
    mastery_claim: false,
    trend: id === "C3" ? "stable" : "unknown",
    attempt_count: id === "C3" ? 2 : 0,
    pass_count: id === "C3" ? 1 : 0,
    fail_count: id === "C3" ? 1 : 0,
    transfer: { attempts: 0, successes: 0, failures: 0, success_rate: 0 },
    hint_dependence: 0,
    hint_count: 0,
    recent_history: [],
    active_misconception_count: 0,
  });
  return {
    session_id: "sess-home",
    language_track: "python",
    concepts: [
      card("C1", "Variables, Types, Operators, I/O", "Foundations"),
      card("C2", "Conditionals & Boolean Logic", "Control Flow"),
      card("C3", "Loops & Iteration Control", "Control Flow"),
      card("C4", "Functions / Methods, Parameters, Scope & Return", "Functions"),
      card("C5", "Lists / Arrays & Strings", "Collections"),
      card("C6", "Dictionaries / Maps, Sets & Nested Structures", "Collections"),
      card("C7", "OOP: Classes, Objects, Encapsulation, Inheritance", "Objects"),
      card("C8", "Recursion, Exceptions & Algorithmic Complexity Basics", "Recursion & Beyond"),
    ],
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
    session_id: "sess-home",
    total: 1,
    limit: 5,
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
    ],
  };
}

function renderHome() {
  return render(
    <SessionProvider>
      <SiteHeader />
      <HomePage />
    </SessionProvider>,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

test("navigation shows all five areas", async () => {
  vi.stubGlobal("fetch", mockFetch({ "POST /student/sessions": sessionPayload() }));
  renderHome();
  const nav = await screen.findByRole("navigation", { name: "Primary" });
  for (const label of ["Home", "Learn", "Practice", "Progress", "History"]) {
    expect(within(nav).getByRole("link", { name: label })).toBeDefined();
  }
  const current = nav.querySelector('a[aria-current="page"]');
  expect(current?.textContent).toBe("Home");
});

test("home answers what to do next from the live journey", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/journey?session_id=sess-home": journeyPayload(),
    }),
  );
  renderHome();
  expect(await screen.findByText("Welcome to Cognify")).toBeDefined();
  expect(await screen.findByText("Keep working on the problem")).toBeDefined();
  expect(await screen.findByText("Count Divisible Numbers")).toBeDefined();
  // Humanized recommendation: natural language, no internal codes.
  expect(
    await screen.findByText("Practice a simpler variant of this idea first."),
  ).toBeDefined();
  expect(screen.queryByText(/C3-M01/)).toBeNull();
  expect(screen.queryByText("REMEDIAL_PROBLEM")).toBeNull();
});

test("home shows an honest empty recommendation state", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/journey?session_id=sess-home": {
        ...journeyPayload(),
        recommendations: [],
      },
    }),
  );
  renderHome();
  expect(await screen.findByText("No recommendation yet")).toBeDefined();
});

test("home enriches with concept levels and recent activity", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/journey?session_id=sess-home": {
        ...journeyPayload(),
        recommendations: [],
      },
      "GET /student/concepts?session_id=sess-home": conceptsPayload(),
      "GET /student/history?session_id=sess-home&limit=5": historyPayload(),
    }),
  );
  renderHome();
  // Backend next_action (not the journey list) drives the recommendation.
  expect(
    await screen.findByText("Keep practicing this concept to make it stick."),
  ).toBeDefined();
  expect(await screen.findByText("Where you stand")).toBeDefined();
  expect(await screen.findByText(/2 attempts/)).toBeDefined();
  expect(await screen.findByText("Recent activity")).toBeDefined();
  expect(await screen.findByText(/Needs another attempt/)).toBeDefined();
  expect(screen.queryByText(/C3-M01/)).toBeNull();
});

test("home still answers when enrichment fetches fail", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/journey?session_id=sess-home": journeyPayload(),
    }),
  );
  renderHome();
  // Journey state alone still answers "what's next".
  expect(await screen.findByText("Keep working on the problem")).toBeDefined();
  expect(
    await screen.findByText("Practice a simpler variant of this idea first."),
  ).toBeDefined();
});

test("home reports backend failure without fake content", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({ "POST /student/sessions": new Error("down") }),
  );
  renderHome();
  await waitFor(() =>
    expect(screen.queryByText("Keep working on the problem")).toBeNull(),
  );
  expect(await screen.findByText(/Couldn't start your session/)).toBeDefined();
});

test("language track is visible and clearly selected", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "GET /student/journey?session_id=sess-home": journeyPayload(),
    }),
  );
  renderHome();
  expect(await screen.findByText("Python track")).toBeDefined();
  const group = await screen.findByRole("group", { name: "Language track" });
  const python = within(group).getByRole("button", { name: "Python" });
  const java = within(group).getByRole("button", { name: "Java" });
  expect(python.getAttribute("aria-pressed")).toBe("true");
  expect(java.getAttribute("aria-pressed")).toBe("false");
});
