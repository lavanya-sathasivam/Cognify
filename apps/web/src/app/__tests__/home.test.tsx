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
