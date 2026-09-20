/** Practice humanization tests (Step 20A).
 *
 * Normal UI must never show internal codes (misconception IDs, action
 * types, intervention types); the ?debug=1 view may reveal them.
 * Also covers the per-test result list and keyboard submission.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { SiteHeader } from "../../../components/layout";
import { SessionProvider } from "../../../components/session";
import PracticePage from "../page";

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
    session_id: "sess-human",
    language_track: "python",
    journey_state: {
      stage: "started",
      canonical_passed: false,
      transfer_available: false,
      band: "novice",
      mastery_claim: false,
    },
    problem: PROBLEM,
  };
}

function failedPayload() {
  return {
    session_id: "sess-human",
    problem_id: PROBLEM.problem_id,
    variant_role: "canonical",
    outcome: "FAILED",
    execution: {
      status: "FAILED",
      passed_count: 2,
      failed_count: 3,
      failed_test_id: "P2",
      tests: [
        { test_id: "P1", passed: true, is_hidden: false },
        {
          test_id: "P2",
          passed: false,
          is_hidden: false,
          input: "4 3\n3 6 7 9\n",
          expected_output: "3",
          actual_output: "2\n",
        },
        { test_id: "H1", passed: false, is_hidden: true },
      ],
    },
    diagnosis: {
      misconception_id: "C3-M01",
      explanation: "The loop skips the last element.",
      confidence: 0.7,
      confidence_label: "likely",
      evidence_summary: { failed_test_id: "P2" },
      source: "fallback",
    },
    intervention: {
      misconception_id: "C3-M01",
      intervention_level: "L1",
      intervention_type: "BOUNDARY_CHECK",
      target_skill: "loop-boundary-checks",
      explanation: "L1 nudge.",
      recommended_action: "Trace the loop on the decisive input.",
      student_message: "Check whether your loop processes the final element.",
    },
    recommendations: [],
    transfer_available: false,
    transfer_problem: null,
    verification: null,
    journey_state: {
      stage: "practicing",
      canonical_passed: false,
      transfer_available: false,
      band: "novice",
      mastery_claim: false,
    },
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

function renderPractice() {
  return render(
    <SessionProvider>
      <SiteHeader />
      <PracticePage />
    </SessionProvider>,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

afterEach(() => {
  window.history.replaceState({}, "", "/");
});

async function submitFailed() {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "POST /student/submissions": failedPayload(),
    }),
  );
  renderPractice();
  await screen.findByRole("button", { name: "Submit" });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  await screen.findByText("Your code needs improvement");
}

test("normal UI hides internal codes", async () => {
  await submitFailed();
  expect(screen.queryByText("C3-M01")).toBeNull();
  expect(screen.queryByText("BOUNDARY_CHECK")).toBeNull();
  expect(screen.queryByText("loop-boundary-checks")).toBeNull();
  // Student language is shown instead.
  expect(
    await screen.findByText(/Check whether your loop processes/),
  ).toBeDefined();
});

test("per-test results list visible and hidden outcomes", async () => {
  await submitFailed();
  expect(await screen.findByText("Test P1 — passed")).toBeDefined();
  expect(await screen.findByText("Test P2 — did not pass")).toBeDefined();
  // The hidden-test row carries an extra "(hidden test)" suffix, so match
  // by pattern rather than exact text.
  expect(await screen.findByText(/Test H1/)).toBeDefined();
  // Hidden test details stay hidden; visible ones show evidence.
  expect(await screen.findByText(/stay hidden/)).toBeDefined();
});

test("debug mode reveals developer details", async () => {
  window.history.replaceState({}, "", "/practice?debug=1");
  await submitFailed();
  // Both the feedback block and the intervention card expose raw values.
  expect((await screen.findAllByText(/Developer details/)).length).toBeGreaterThan(0);
  expect((await screen.findAllByText(/C3-M01/)).length).toBeGreaterThan(0);
});

test("ctrl+enter submits the code", async () => {
  const fetchMock = mockFetch({
    "POST /student/sessions": sessionPayload(),
    "POST /student/submissions": failedPayload(),
  });
  vi.stubGlobal("fetch", fetchMock);
  renderPractice();
  const editor = (await screen.findByLabelText(
    "Your Python code",
  )) as HTMLTextAreaElement;
  fireEvent.keyDown(editor, { key: "Enter", ctrlKey: true });
  expect(await screen.findByText("Your code needs improvement")).toBeDefined();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
