/** Learn / Progress / History page tests (Step 20A).
 *
 * Learn shows the eight real curriculum concepts with honest states (only
 * C3 is live). Progress uses level labels, never raw numbers. History is
 * an honest empty state until backend history support lands.
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

function journeyPayload() {
  return {
    session_id: "sess-pages",
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
    recommendations: [],
  };
}

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const key = `${method} ${String(url).replace(/^https?:\/\/[^/]+/, "")}`;
    if (!(key in routes)) throw new Error(`unexpected request: ${key}`);
    return { ok: true, status: 200, json: async () => routes[key] };
  });
}

function routes() {
  return {
    "POST /student/sessions": sessionPayload(),
    "GET /student/journey?session_id=sess-pages": journeyPayload(),
  };
}

beforeEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

test("learn roadmap lists all eight concepts with honest states", async () => {
  vi.stubGlobal("fetch", mockFetch(routes()));
  render(
    <SessionProvider>
      <LearnPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Learn Python")).toBeDefined();
  for (const id of ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]) {
    expect(await screen.findByText(new RegExp(`^${id} ·`))).toBeDefined();
  }
  // Live C3 state uses a level label; everything else is honestly pending.
  expect(await screen.findByText("Developing")).toBeDefined();
  expect(screen.getAllByText("Not started yet").length).toBeGreaterThanOrEqual(7);
  // No fabricated gamification or locks ("expressions" contains "xp",
  // hence word boundaries).
  expect(screen.queryByText(/\bXP\b|\bstreak\b|\blocked\b|\bbadge/i)).toBeNull();
});

test("progress shows level labels, never raw mastery numbers", async () => {
  vi.stubGlobal("fetch", mockFetch(routes()));
  render(
    <SessionProvider>
      <ProgressPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Your progress")).toBeDefined();
  expect(await screen.findByText("Developing")).toBeDefined();
  expect(await screen.findByText("Not yet — keep practicing")).toBeDefined();
  expect(screen.queryByText(/Mastery =|0\.\d+/)).toBeNull();
  expect(screen.getAllByText("Not started yet").length).toBe(7);
});

test("history is an honest empty state without invented data", async () => {
  vi.stubGlobal("fetch", mockFetch(routes()));
  render(
    <SessionProvider>
      <HistoryPage />
    </SessionProvider>,
  );
  expect(await screen.findByText("Your history")).toBeDefined();
  expect(await screen.findByText("No learning history yet")).toBeDefined();
  expect(
    await screen.findByText(/backend history support is added/),
  ).toBeDefined();
});
