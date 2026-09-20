/** Cognify student API client (Step 16 vertical slice).
 *
 * Typed wrappers around the core-backend student endpoints. No intelligence
 * lives here: the server resolves problems, executes code in its sandbox,
 * diagnoses, intervenes, verifies, and recommends. This module only moves
 * JSON and surfaces HTTP failures as ApiError.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_CORE_BACKEND_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Backend unreachable. Is core-backend running?");
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${response.status}).`;
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

export interface ProblemView {
  problem_id: string;
  language: string;
  concept_id: string;
  title: string;
  statement: string;
  constraints: string[];
  input_format: string;
  output_format: string;
  starter_code: string;
  difficulty: number;
}

export interface TestResultView {
  test_id: string;
  passed: boolean;
  is_hidden?: boolean;
  input?: string | null;
  expected_output?: string | null;
  actual_output?: string | null;
}

export interface ExecutionView {
  status: string;
  passed_count: number;
  failed_count: number;
  failed_test_id: string | null;
  expected_output?: string | null;
  actual_output?: string | null;
  stderr?: string | null;
  tests: TestResultView[];
}

export interface DiagnosisView {
  misconception_id: string;
  explanation: string;
  confidence: number;
  confidence_label: "likely" | "possible" | "uncertain";
  evidence_summary: { failed_test_id: string | null };
  source: string;
}

export interface InterventionView {
  misconception_id: string;
  intervention_level: string;
  intervention_type: string;
  target_skill: string;
  explanation: string;
  recommended_action: string;
  student_message: string;
}

export interface RecommendationView {
  action: string | null;
  reason: string | null;
  problem_id: string | null;
  problem_title: string | null;
}

export interface VerificationView {
  outcome: string;
  message: string;
}

export interface JourneyStateView {
  stage: string;
  canonical_passed: boolean;
  transfer_available: boolean;
  band: string;
  mastery_claim: boolean;
}

export interface SubmissionResponse {
  session_id: string;
  problem_id: string;
  variant_role: string;
  outcome: string;
  execution: ExecutionView;
  diagnosis: DiagnosisView | null;
  intervention: InterventionView | null;
  recommendations: RecommendationView[];
  transfer_available: boolean;
  transfer_problem: ProblemView | null;
  verification: VerificationView | null;
  journey_state: JourneyStateView;
}

export interface SessionResponse {
  session_id: string;
  language_track: string;
  journey_state: JourneyStateView;
  problem: ProblemView;
}

export interface JourneyResponse {
  session_id: string;
  language_track: string;
  canonical_problem_id: string;
  transfer_problem_id: string;
  journey_state: JourneyStateView;
  verification: VerificationView | null;
  recommendations: RecommendationView[];
}

export const api = {
  createSession(): Promise<SessionResponse> {
    return request<SessionResponse>("/student/sessions", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },
  submit(
    sessionId: string,
    problemId: string,
    code: string,
  ): Promise<SubmissionResponse> {
    return request<SubmissionResponse>("/student/submissions", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        problem_id: problemId,
        code,
      }),
    });
  },
  getJourney(sessionId: string): Promise<JourneyResponse> {
    return request<JourneyResponse>(
      `/student/journey?session_id=${encodeURIComponent(sessionId)}`,
    );
  },
  getProblem(sessionId: string, problemId: string): Promise<ProblemView> {
    return request<ProblemView>(
      `/student/problems/${encodeURIComponent(problemId)}?session_id=${encodeURIComponent(sessionId)}`,
    );
  },
};

export function friendlyError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return error.message;
    if (error.status === 409)
      return "Finish the current problem before moving on to the next one.";
    if (error.status === 503)
      return "Code execution is temporarily unavailable. Please try again.";
    return error.message;
  }
  return "Something went wrong. Please try again.";
}
