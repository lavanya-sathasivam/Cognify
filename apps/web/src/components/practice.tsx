/** Practice-screen building blocks (Step 20A).
 *
 * Problem display, code editing, test results, feedback, and next-step
 * cards. All text shown to students is either server-provided prose or the
 * humanized copy in `lib/copy`; internal codes appear only inside
 * `DebugDetails`, which renders solely under `?debug=1`.
 */
import type { KeyboardEvent } from "react";
import type {
  ExecutionView,
  InterventionView,
  ProblemView,
  RecommendationView,
  SubmissionResponse,
  TestResultView,
} from "../app/lib/api";
import {
  actionVerb as actionCopy,
  humanizeReason as humanReason,
  isDebugMode as debugMode,
} from "../app/lib/copy";
import { Card, Mark, PrimaryButton, SecondaryButton } from "./ui";

export function ProblemPanel({ problem }: { problem: ProblemView }) {
  return (
    <Card label="Problem">
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
    </Card>
  );
}

export function CodeEditor({
  code,
  busy,
  sessionReady,
  onChange,
  onSubmit,
  language,
}: {
  code: string;
  busy: boolean;
  sessionReady: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  language?: string;
}) {
  const handleKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      onSubmit();
    }
  };
  const langLabel = language === "java" ? "Java" : "Python";
  return (
    <Card label="Code editor">
      <label
        htmlFor="code-editor"
        className="text-sm font-medium text-zinc-700 dark:text-zinc-200"
      >
        Your {langLabel} code
      </label>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Press Cmd/Ctrl + Enter to submit.
      </p>
      <textarea
        id="code-editor"
        value={code}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        rows={14}
        spellCheck={false}
        className="mt-2 w-full rounded-md border border-zinc-300 bg-zinc-50 p-3 font-mono text-sm leading-5 dark:border-zinc-700 dark:bg-black"
      />
      <div className="sticky bottom-0 -mx-5 -mb-5 mt-3 flex items-center gap-3 border-t border-zinc-200 bg-white/95 px-5 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/95">
        <PrimaryButton onClick={onSubmit} disabled={busy || !sessionReady}>
          {busy ? "Running…" : "Submit"}
        </PrimaryButton>
        {busy && (
          <span className="text-sm text-zinc-500" role="status">
            Executing your code against the tests…
          </span>
        )}
      </div>
    </Card>
  );
}

export function TestList({ execution }: { execution: ExecutionView }) {
  if (!execution.tests || execution.tests.length === 0) {
    return (
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
        {execution.passed_count} passed · {execution.failed_count} failed
      </p>
    );
  }
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {execution.tests.map((t: TestResultView) => (
        <li
          key={t.test_id}
          className="flex items-start gap-2 rounded-md border border-zinc-200 p-2.5 text-sm dark:border-zinc-800"
        >
          <Mark kind={t.passed ? "pass" : "fail"} />
          <div className="min-w-0">
            <p className="font-medium">
              Test {t.test_id} — {t.passed ? "passed" : "did not pass"}
              {t.is_hidden ? " (hidden test)" : ""}
            </p>
            {!t.passed && !t.is_hidden && (t.input != null || t.actual_output != null) && (
              <p className="mt-1 font-mono text-xs text-zinc-600 dark:text-zinc-300">
                {t.input != null && <>input: {t.input} · </>}
                {t.expected_output != null && <>expected: {t.expected_output} · </>}
                {t.actual_output != null && <>got: {t.actual_output}</>}
              </p>
            )}
            {!t.passed && t.is_hidden && (
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                This test&apos;s details stay hidden — check the general
                feedback above.
              </p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Raw internal values, rendered only under ?debug=1. Never part of normal UI. */
export function DebugDetails({ data }: { data: Record<string, unknown> }) {
  if (!debugMode()) return null;
  return (
    <details className="mt-4 rounded-md bg-zinc-100 p-3 text-xs dark:bg-zinc-900">
      <summary className="cursor-pointer font-medium">
        Developer details (debug only)
      </summary>
      <pre className="mt-2 overflow-x-auto font-mono">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

export function RecommendationList({
  recommendations,
  debugContext,
}: {
  recommendations: RecommendationView[];
  debugContext?: Record<string, unknown>;
}) {
  if (recommendations.length === 0) return null;
  return (
    <div className="mt-4">
      <h3 className="text-sm font-medium">Next recommended step</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {recommendations.slice(0, 3).map((rec, i) => (
          <li
            key={`${rec.action}-${rec.problem_id ?? i}`}
            className="rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800"
          >
            <p className="font-medium">{actionCopy(rec.action)}</p>
            {rec.problem_title && (
              <p className="mt-1">Problem: {rec.problem_title}</p>
            )}
            {rec.reason && (
              <p className="mt-1 text-zinc-600 dark:text-zinc-300">
                {humanReason(rec.reason)}
              </p>
            )}
          </li>
        ))}
      </ul>
      {debugContext && <DebugDetails data={debugContext} />}
    </div>
  );
}

function certaintyHeading(label: string): string {
  if (label === "likely") return "Likely cause";
  if (label === "possible") return "Possible cause";
  return "Not certain — one possible cause";
}

function FailedFeedback({
  result,
  onRetry,
}: {
  result: SubmissionResponse;
  onRetry: () => void;
}) {
  const { execution } = result;
  return (
    <div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Let&apos;s look at what happened.
      </p>
      <h2 className="mt-1 text-lg font-semibold">
        Your code needs improvement
      </h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
        You passed {execution.passed_count} of{" "}
        {execution.passed_count + execution.failed_count} tests.
        {execution.failed_test_id
          ? ` First failure on test ${execution.failed_test_id}.`
          : ""}
      </p>
      <TestList execution={execution} />
      {result.diagnosis ? (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Why your code failed</h3>
          <p className="mt-1 text-sm font-medium text-zinc-700 dark:text-zinc-200">
            {certaintyHeading(result.diagnosis.confidence_label)}:
          </p>
          <p className="mt-1 text-sm leading-6">
            {result.diagnosis.explanation}
          </p>
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
        <InterventionCard intervention={result.intervention} />
      )}
      <SecondaryButton onClick={onRetry} className="mt-4">
        Retry
      </SecondaryButton>
      <DebugDetails
        data={{
          misconception_id: result.diagnosis?.misconception_id ?? null,
          intervention_type: result.intervention?.intervention_type ?? null,
        }}
      />
    </div>
  );
}

export function InterventionCard({
  intervention,
}: {
  intervention: InterventionView;
}) {
  return (
    <div className="mt-4 rounded-lg border border-teal-200 bg-teal-50 p-4 dark:border-teal-800 dark:bg-teal-950">
      <h3 className="text-sm font-medium">What to try</h3>
      <p className="mt-1 text-sm font-medium text-zinc-700 dark:text-zinc-200">
        Something to check: {intervention.student_message}
      </p>
      <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
        {intervention.recommended_action}
      </p>
      <DebugDetails
        data={{
          misconception_id: intervention.misconception_id,
          intervention_type: intervention.intervention_type,
          target_skill: intervention.target_skill,
        }}
      />
    </div>
  );
}

export function ResultPanel({
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
            <p className="text-sm font-medium">
              Try a related problem to check the idea holds in a new context
            </p>
            <PrimaryButton onClick={onContinue} className="mt-2">
              Continue
            </PrimaryButton>
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
        <RecommendationList
          recommendations={result.recommendations}
          debugContext={{
            verification_outcome: result.verification.outcome,
            actions: result.recommendations.map((r) => r.action),
          }}
        />
      </div>
    );
  }

  if (result.outcome === "FAILED") {
    return <FailedFeedback result={result} onRetry={onRetry} />;
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
      <SecondaryButton onClick={onRetry} className="mt-4">
        Retry
      </SecondaryButton>
    </div>
  );
}
