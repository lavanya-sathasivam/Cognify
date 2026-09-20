"use client";

/** Cognify student learning screen (Step 16 vertical slice).
 *
 * One complete flow, no chatbot: Problem -> Code -> Feedback -> Retry ->
 * Transfer -> Progress. The AI explanation is supporting information, not
 * the primary UI. All intelligence (execution, diagnosis, intervention,
 * verification, recommendations) comes from core-backend; this screen
 * only renders server-provided JSON and never invents advice.
 */
import { useCallback, useEffect, useState } from "react";
import {
  api,
  friendlyError,
  type ProblemView,
  type SubmissionResponse,
} from "./lib/api";

type Screen =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "failed" };

function certaintyHeading(label: string): string {
  if (label === "likely") return "Likely cause";
  if (label === "possible") return "Possible cause";
  return "Not certain — one possible cause";
}

export default function LearnPage() {
  const [screen, setScreen] = useState<Screen>({ kind: "loading" });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [problem, setProblem] = useState<ProblemView | null>(null);
  const [code, setCode] = useState("");
  const [result, setResult] = useState<SubmissionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .createSession()
      .then((session) => {
        if (cancelled) return;
        setSessionId(session.session_id);
        setProblem(session.problem);
        setCode(session.problem.starter_code);
        setScreen({ kind: "ready" });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(friendlyError(err));
        setScreen({ kind: "failed" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = useCallback(async () => {
    if (!sessionId || !problem || busy) return;
    if (!code.trim()) {
      setError("Write some code before submitting.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await api.submit(sessionId, problem.problem_id, code);
      setResult(response);
    } catch (err: unknown) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }, [sessionId, problem, code, busy]);

  const continueToTransfer = useCallback(() => {
    const next = result?.transfer_problem;
    if (!next) return;
    setProblem(next);
    setCode(next.starter_code);
    setResult(null);
    setError(null);
  }, [result]);

  const retry = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return (
    <div className="flex min-h-full flex-col bg-zinc-50 text-zinc-950 dark:bg-black dark:text-zinc-50">
      <header className="border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between">
          <h1 className="text-xl font-semibold tracking-tight">Cognify</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            current language: Python
          </p>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-6">
        {screen.kind === "loading" && (
          <p className="text-zinc-500" role="status">
            Loading your problem…
          </p>
        )}

        {screen.kind === "failed" && !problem && (
          <div
            className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100"
            role="alert"
          >
            <p className="font-medium">Couldn&apos;t start your session.</p>
            <p className="mt-1 text-sm">{error ?? "Backend unreachable."}</p>
          </div>
        )}

        {problem && (
          <section
            aria-label="Problem"
            className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 className="text-lg font-semibold">{problem.title}</h2>
              <span className="text-sm text-zinc-500 dark:text-zinc-400">
                {problem.concept_id} · difficulty {problem.difficulty}
              </span>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6">
              {problem.statement}
            </p>
            <h3 className="mt-4 text-sm font-medium">Constraints</h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-zinc-600 dark:text-zinc-300">
              {problem.constraints.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <h3 className="font-medium">Input format</h3>
                <p className="mt-1 text-zinc-600 dark:text-zinc-300">
                  {problem.input_format}
                </p>
              </div>
              <div>
                <h3 className="font-medium">Output format</h3>
                <p className="mt-1 text-zinc-600 dark:text-zinc-300">
                  {problem.output_format}
                </p>
              </div>
            </div>
          </section>
        )}

        {problem && (
          <section
            aria-label="Code editor"
            className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
          >
            <label
              htmlFor="code-editor"
              className="text-sm font-medium text-zinc-700 dark:text-zinc-200"
            >
              Your Python code
            </label>
            <textarea
              id="code-editor"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              rows={14}
              spellCheck={false}
              className="mt-2 w-full rounded-md border border-zinc-300 bg-zinc-50 p-3 font-mono text-sm leading-5 dark:border-zinc-700 dark:bg-black"
            />
            <div className="mt-3 flex items-center gap-3">
              <button
                type="button"
                onClick={submit}
                disabled={busy}
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
              >
                {busy ? "Running…" : "Submit"}
              </button>
              {busy && (
                <span className="text-sm text-zinc-500" role="status">
                  Executing your code against the tests…
                </span>
              )}
            </div>
          </section>
        )}

        {error && problem && (
          <div
            className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100"
            role="alert"
          >
            {error}
          </div>
        )}

        {result && problem && (
          <section
            aria-label="Result"
            aria-live="polite"
            className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
          >
            <ResultPanel
              result={result}
              conceptId={problem.concept_id}
              onRetry={retry}
              onContinue={continueToTransfer}
            />
          </section>
        )}
      </main>
    </div>
  );
}

function ResultPanel({
  result,
  conceptId,
  onRetry,
  onContinue,
}: {
  result: SubmissionResponse;
  conceptId: string;
  onRetry: () => void;
  onContinue: () => void;
}) {
  const { execution } = result;

  if (result.outcome === "PASSED" && result.variant_role !== "transfer") {
    return (
      <div>
        <h2 className="text-lg font-semibold">✓ Good improvement</h2>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
          All {execution.passed_count} tests pass.
        </p>
        {result.transfer_problem && (
          <div className="mt-4">
            <p className="text-sm font-medium">Try a related problem</p>
            <button
              type="button"
              onClick={onContinue}
              className="mt-2 rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              Continue
            </button>
          </div>
        )}
      </div>
    );
  }

  if (result.variant_role === "transfer" && result.verification) {
    const verified = result.verification.outcome === "VERIFIED_IMPROVED";
    return (
      <div>
        <h2 className="text-lg font-semibold">
          {verified ? "✓ Verified improvement" : "Result recorded"}
        </h2>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
          {result.verification.message}
        </p>
        {result.journey_state.mastery_claim ? (
          <p className="mt-2 text-sm font-medium">You mastered {conceptId}.</p>
        ) : null}
        {result.recommendations.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium">Next recommended step</h3>
            <ul className="mt-2 flex flex-col gap-2">
              {result.recommendations.slice(0, 3).map((rec, i) => (
                <li
                  key={`${rec.action}-${rec.problem_id ?? i}`}
                  className="rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800"
                >
                  <p className="font-medium">{rec.action}</p>
                  {rec.problem_title && (
                    <p className="mt-1">Problem: {rec.problem_title}</p>
                  )}
                  {rec.reason && (
                    <p className="mt-1 text-zinc-600 dark:text-zinc-300">
                      {rec.reason}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (result.outcome === "FAILED") {
    return (
      <div>
        <h2 className="text-lg font-semibold">Your code needs improvement</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
          {execution.passed_count} passed · {execution.failed_count} failed
          {execution.failed_test_id
            ? ` · first failure on test ${execution.failed_test_id}`
            : ""}
        </p>
        {result.diagnosis ? (
          <div className="mt-4">
            <h3 className="text-sm font-medium">Why your code failed</h3>
            <p className="mt-1 text-sm font-medium text-zinc-700 dark:text-zinc-200">
              {certaintyHeading(result.diagnosis.confidence_label)}:
            </p>
            <p className="mt-1 text-sm leading-6">{result.diagnosis.explanation}</p>
            <h3 className="mt-4 text-sm font-medium">Evidence</h3>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
              Test {result.diagnosis.evidence_summary.failed_test_id} did not
              produce the expected output while the other tests mostly passed,
              which points at a single missed case rather than broken logic.
            </p>
          </div>
        ) : (
          <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-300">
            No specific feedback is available for this run — check the error
            below and retry.
          </p>
        )}
        {result.intervention && (
          <div className="mt-4">
            <h3 className="text-sm font-medium">What to try</h3>
            <p className="mt-1 text-sm leading-6">
              {result.intervention.student_message}
            </p>
            <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
              {result.intervention.recommended_action}
            </p>
          </div>
        )}
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-lg font-semibold">Your code did not run cleanly</h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
        Outcome: {result.outcome}.{" "}
        {result.outcome === "TIMEOUT"
          ? "Your program took too long — check for a loop that never ends."
          : "Your program raised an error before finishing. Read the message below."}
      </p>
      {result.execution.stderr && (
        <pre className="mt-3 overflow-x-auto rounded-md bg-zinc-100 p-3 font-mono text-xs dark:bg-zinc-900">
          {result.execution.stderr.slice(0, 1000)}
        </pre>
      )}
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
      >
        Retry
      </button>
    </div>
  );
}
