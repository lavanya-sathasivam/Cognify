/** Step 16 frontend tests, moved to the Practice route (Step 20A).
 *
 * Same vertical slice, same assertions: rendered with React Testing
 * Library + Vitest; network is fully mocked, so these tests assert UI
 * states and transitions, never backend behavior (covered by
 * core-backend tests). Pages now render inside the shared session
 * provider + site header, exactly as the app serves them.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
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

const TRANSFER_PROBLEM = {
  ...PROBLEM,
  problem_id: "PY-C3-COUNT-DIV-TRANSFER",
  title: "Count Cold Days",
  starter_code: "def count_cold_days(temps, threshold):\n    raise NotImplementedError\n",
};

function sessionPayload() {
  return {
    session_id: "sess-1",
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
    session_id: "sess-1",
    problem_id: PROBLEM.problem_id,
    variant_role: "canonical",
    outcome: "FAILED",
    execution: {
      status: "FAILED",
      passed_count: 2,
      failed_count: 3,
      failed_test_id: "P2",
      tests: [],
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

function passedPayload() {
  return {
    ...failedPayload(),
    outcome: "PASSED",
    variant_role: "canonical",
    execution: {
      status: "PASSED",
      passed_count: 5,
      failed_count: 0,
      failed_test_id: null,
      tests: [],
    },
    diagnosis: null,
    intervention: null,
    transfer_available: true,
    transfer_problem: TRANSFER_PROBLEM,
    journey_state: {
      stage: "retry_passed",
      canonical_passed: true,
      transfer_available: true,
      band: "novice",
      mastery_claim: false,
    },
  };
}

function verifiedPayload() {
  return {
    ...passedPayload(),
    problem_id: TRANSFER_PROBLEM.problem_id,
    variant_role: "transfer",
    verification: {
      outcome: "VERIFIED_IMPROVED",
      message: "Nice! You solved the original problem.",
    },
    recommendations: [
      {
        action: "REVIEW_CONCEPT",
        reason: "Keep practicing loops.",
        problem_id: "PY-C3-COUNT-DIV",
        problem_title: "Count Divisible Numbers",
      },
    ],
    journey_state: {
      stage: "transfer_done",
      canonical_passed: true,
      transfer_available: true,
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
    const body = routes[key];
    if (body instanceof Error) throw body;
    return { ok: true, status: 200, json: async () => body };
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

test("problem renders with starter code and submit", async () => {
  vi.stubGlobal("fetch", mockFetch({ "POST /student/sessions": sessionPayload() }));
  renderPractice();
  expect(await screen.findByText("Cognify")).toBeDefined();
  expect(await screen.findByText("Count Divisible Numbers")).toBeDefined();
  expect(await screen.findByText(/Python track/)).toBeDefined();
  const editor = (await screen.findByLabelText(
    "Your Python code",
  )) as HTMLTextAreaElement;
  expect(editor.value).toContain("def count_divisible");
  expect(await screen.findByRole("button", { name: "Submit" })).toBeDefined();
});

test("code can be edited", async () => {
  vi.stubGlobal("fetch", mockFetch({ "POST /student/sessions": sessionPayload() }));
  renderPractice();
  const editor = (await screen.findByLabelText(
    "Your Python code",
  )) as HTMLTextAreaElement;
  fireEvent.change(editor, { target: { value: "my attempt" } });
  expect(editor.value).toBe("my attempt");
});

test("submit shows progress then failure state with intervention", async () => {
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
  expect(await screen.findByText("Running…")).toBeDefined();
  expect(
    await screen.findByText("Your code needs improvement"),
  ).toBeDefined();
  expect(await screen.findByText("Why your code failed")).toBeDefined();
  expect(await screen.findByText("Evidence")).toBeDefined();
  expect(await screen.findByText("What to try")).toBeDefined();
  expect(
    await screen.findByText(/Check whether your loop processes/),
  ).toBeDefined();
  expect(await screen.findByRole("button", { name: "Retry" })).toBeDefined();
});

test("retry flow shows success and transfer continuation", async () => {
  const fetchMock = mockFetch({
    "POST /student/sessions": sessionPayload(),
    "POST /student/submissions": passedPayload(),
  });
  vi.stubGlobal("fetch", fetchMock);
  renderPractice();
  await screen.findByRole("button", { name: "Submit" });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  expect(await screen.findByText("✓ Good improvement")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByText("Count Cold Days")).toBeDefined();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("verified-improvement state shows message and next step", async () => {
  let calls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      calls += 1;
      const body = calls === 1 ? sessionPayload() : verifiedPayload();
      return { ok: true, status: 200, json: async () => body };
    }),
  );
  renderPractice();
  await screen.findByRole("button", { name: "Submit" });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  expect(await screen.findByText("✓ Verified improvement")).toBeDefined();
  expect(await screen.findByText("Next recommended step")).toBeDefined();
  expect(await screen.findByText("Count Divisible Numbers")).toBeDefined();
});

test("backend failure shows an error, never silent success", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({ "POST /student/sessions": new Error("down") }),
  );
  renderPractice();
  expect(await screen.findByText(/Couldn't start your session/)).toBeDefined();
  expect(screen.queryByText("✓ Good improvement")).toBeNull();
});

test("practice heading, steps, and problem context without raw ids", async () => {
  vi.stubGlobal("fetch", mockFetch({ "POST /student/sessions": sessionPayload() }));
  renderPractice();
  expect(await screen.findByText("Practice Python")).toBeDefined();
  expect(
    await screen.findByRole("list", { name: "Practice progress" }),
  ).toBeDefined();
  expect(await screen.findByText("Loops & Iteration Control")).toBeDefined();
  expect(await screen.findByText("Core practice")).toBeDefined();
  expect(screen.queryByText(/C3 ·/)).toBeNull();
});

test("verified state explains the meaning in student language", async () => {
  let calls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      calls += 1;
      const body = calls === 1 ? sessionPayload() : verifiedPayload();
      return { ok: true, status: 200, json: async () => body };
    }),
  );
  renderPractice();
  await screen.findByRole("button", { name: "Submit" });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  expect(await screen.findByText("✓ Verified improvement")).toBeDefined();
  expect(
    await screen.findByText(/applied the idea to a related problem/),
  ).toBeDefined();
  expect(screen.queryByText("VERIFIED_IMPROVED")).toBeNull();
});

test("submission error surfaces the backend message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST" && String(url).endsWith("/student/submissions")) {
        return {
          ok: false,
          status: 409,
          json: async () => ({ detail: "Transfer is unavailable" }),
        };
      }
      return { ok: true, status: 200, json: async () => sessionPayload() };
    }),
  );
  renderPractice();
  await screen.findByRole("button", { name: "Submit" });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toMatch(/before moving on/),
  );
});

test("failure shows what Cognify suggests next without engine values", async () => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": sessionPayload(),
      "POST /student/submissions": {
        ...failedPayload(),
        recommendations: [
          {
            action: "REMEDIAL_PROBLEM",
            reason:
              "C3 mastery is 0.12, below 0.40: review the concept and attempt targeted remedial practice.",
            problem_id: "PY-C3-LOOP-MISCONCEPTION",
            problem_title: "Sum One to N",
          },
        ],
      },
    }),
  );
  renderPractice();
  await screen.findByRole("button", { name: "Submit" });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  expect(await screen.findByText("What Cognify suggests next")).toBeDefined();
  expect(
    await screen.findByText("Practice a simpler variant of this idea first."),
  ).toBeDefined();
  expect(await screen.findByText(/still building/i)).toBeDefined();
  expect(await screen.findByText(/Sum One to N/)).toBeDefined();
  expect(screen.queryByText(/0\.12/)).toBeNull();
  expect(screen.queryByText(/C3 mastery/)).toBeNull();
  expect(screen.queryByText(/C[1-8]-M\d{2}/)).toBeNull();
});

test("java track stays java-only across the practice screen", async () => {
  const javaProblem = {
    ...PROBLEM,
    problem_id: "JAVA-C3-COUNT-DIV",
    language: "java",
    title: "Count Divisible Numbers",
    starter_code:
      "public class CountDivisible {\n    // solve here\n}\n",
  };
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "POST /student/sessions": {
        ...sessionPayload(),
        session_id: "sess-java",
        language_track: "java",
        problem: javaProblem,
      },
    }),
  );
  renderPractice();
  expect(await screen.findByText("Practice Java")).toBeDefined();
  expect(await screen.findByText("Java track")).toBeDefined();
  const editor = (await screen.findByLabelText(
    "Your Java code",
  )) as HTMLTextAreaElement;
  expect(editor.value).toContain("CountDivisible");
  expect(screen.queryByLabelText("Your Python code")).toBeNull();
  expect(screen.queryByText(/Practice Python/)).toBeNull();
});
