/** Progress: how learning is going (Step 20B).
 *
 * Real learner overview from GET /student/concepts: level labels (never
 * raw numbers), trends, attempts, recent performance, transfer, and hint
 * reliance in plain language, plus the adaptive engine's current
 * recommendation. Mastery is claimed only when the backend's
 * mastery_claim says so — "current level" and "mastered" stay distinct.
 */
"use client";

import { useEffect, useState } from "react";
import { NextStepCard } from "../../components/cards";
import {
  Alert,
  Card,
  EmptyState,
  LevelLabel,
  Loading,
  PageHeading,
  SecondaryButton,
} from "../../components/ui";
import { useSession } from "../../components/session";
import { api, friendlyError, type ConceptsResponse } from "../lib/api";
import {
  hintRelianceCopy,
  isDebugMode,
  transferCopy,
  trendLabel,
} from "../lib/copy";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: ConceptsResponse }
  | { kind: "failed"; error: string };

export default function ProgressPage() {
  const { status, sessionId } = useSession();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    if (status !== "ready" || !sessionId) return;
    let cancelled = false;
    // Initial state is already "loading"; async completions below are the
    // only in-effect state updates (no synchronous reset).
    api
      .getConcepts(sessionId)
      .then((data) => {
        if (!cancelled) setState({ kind: "ready", data });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ kind: "failed", error: friendlyError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [status, sessionId]);

  if (status === "loading" || state.kind === "loading") {
    return <Loading text="Loading your progress…" />;
  }

  if (state.kind === "failed") {
    return (
      <div className="flex max-w-3xl flex-col gap-6">
        <PageHeading
          title="Your progress"
          intro="What you've practiced, where you stand, and what to do next — based only on your actual attempts."
        />
        <Alert title="Couldn't load your progress.">
          <p>{state.error}</p>
          <div className="mt-3">
            <SecondaryButton
              onClick={() => {
                if (!sessionId) return;
                setState({ kind: "loading" });
                api
                  .getConcepts(sessionId)
                  .then((data) => setState({ kind: "ready", data }))
                  .catch((err: unknown) =>
                    setState({ kind: "failed", error: friendlyError(err) }),
                  );
              }}
            >
              Try again
            </SecondaryButton>
          </div>
        </Alert>
      </div>
    );
  }

  const concepts = state.data.concepts;
  const started = concepts.filter((c) => c.status === "started");
  const next = state.data.next_action;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeading
        title="Your progress"
        intro="What you've practiced, where you stand, and what to do next — based only on your actual attempts."
      />

      {started.length === 0 ? (
        <EmptyState
          title="No progress yet"
          body="Submit a solution on the Practice page and your progress will appear here."
        />
      ) : (
          started.map((concept) => {
            const recent = concept.recent_history.slice(-3);
            const passed = recent.filter((r) => r.passed).length;
            return (
              <Card key={concept.concept_id} label={concept.title}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-base font-semibold">{concept.title}</h2>
                  <LevelLabel band={concept.band} />
                </div>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                  <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      Current level
                    </dt>
                    <dd className="mt-0.5 font-medium">
                      {concept.mastery_claim
                        ? "Strong — concept mastered"
                        : "Not yet mastered — keep practicing"}
                    </dd>
                  </div>
                  <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
                    <dt className="text-zinc-500 dark:text-zinc-400">Trend</dt>
                    <dd className="mt-0.5 font-medium">
                      {trendLabel(concept.trend)}
                    </dd>
                  </div>
                  <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      Attempts
                    </dt>
                    <dd className="mt-0.5 font-medium">
                      {concept.attempt_count}{" "}
                      {concept.attempt_count === 1 ? "attempt" : "attempts"} ·{" "}
                      {concept.pass_count} solved · {concept.fail_count} to
                      retry
                      {recent.length > 0 &&
                        ` · ${passed} of ${recent.length} recent correct`}
                    </dd>
                  </div>
                  <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      Transfer
                    </dt>
                    <dd className="mt-0.5 font-medium">
                      {transferCopy(
                        concept.transfer.attempts,
                        concept.transfer.successes,
                      )}
                    </dd>
                  </div>
                </dl>
                <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-300">
                  {hintRelianceCopy(
                    concept.hint_dependence,
                    concept.hint_count,
                  )}
                </p>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
                  {concept.active_misconception_count > 0
                    ? `${concept.active_misconception_count} ${concept.active_misconception_count === 1 ? "area" : "areas"} still needs attention — see your next recommended step below.`
                    : "No active weak areas right now."}
                </p>
              {isDebugMode() && (
                <pre className="mt-3 overflow-x-auto rounded-md bg-zinc-100 p-3 font-mono text-xs dark:bg-zinc-900">
                  {JSON.stringify(concept, null, 2)}
                </pre>
              )}
            </Card>
          );
        })
      )}

      {next && (
        <NextStepCard
          recommendation={{
            action: next.action,
            reason: next.reason,
            problem_id: next.problem_id,
            problem_title: next.problem_title,
          }}
        />
      )}
      <section aria-label="Not started">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          Still ahead
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {concepts
            .filter((c) => c.status === "not_started")
            .map((c) => (
              <Card key={c.concept_id} label={c.title}>
                <h3 className="text-sm font-semibold">{c.title}</h3>
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  Not started yet — no attempts recorded.
                </p>
              </Card>
            ))}
        </div>
      </section>
    </div>
  );
}
