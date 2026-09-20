/** Progress: how learning is going (Step 20A).
 *
 * C3 reflects the live journey state with level labels instead of raw
 * numbers; mastery is claimed only when the backend's mastery_claim says
 * so. All other concepts show honest not-started states until per-concept
 * backend support lands (Step 20B).
 */
"use client";

import { useEffect } from "react";
import { NextStepCard } from "../../components/cards";
import { Card, EmptyState, LevelLabel, Loading, PageHeading } from "../../components/ui";
import { useSession } from "../../components/session";
import { CONCEPT_GROUPS } from "../lib/concepts";

export default function ProgressPage() {
  const { status, journey, session, refresh } = useSession();

  useEffect(() => {
    if (status === "ready") {
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  if (status === "loading") {
    return <Loading text="Loading your progress…" />;
  }

  const state = journey?.journey_state ?? session?.journey_state ?? null;
  const next = journey?.recommendations?.[0] ?? null;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeading
        title="Your progress"
        intro="What you've practiced, where you stand, and what to do next — based only on your actual attempts."
      />

      {state ? (
        <Card label="Loops and iteration control">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold">
              C3 · Loops &amp; Iteration Control
            </h2>
            <LevelLabel band={state.band} />
          </div>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
              <dt className="text-zinc-500 dark:text-zinc-400">Stage</dt>
              <dd className="mt-0.5 font-medium">
                {state.stage === "started" && "Just getting started"}
                {state.stage === "practicing" && "Practicing"}
                {state.stage === "retry_passed" && "Original solved"}
                {state.stage === "transfer_done" && "Challenge completed"}
              </dd>
            </div>
            <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
              <dt className="text-zinc-500 dark:text-zinc-400">Mastery</dt>
              <dd className="mt-0.5 font-medium">
                {state.mastery_claim
                  ? "Strong — concept mastered"
                  : "Not yet — keep practicing"}
              </dd>
            </div>
          </dl>
          {state.transfer_available && !state.mastery_claim && (
            <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-300">
              A related problem is available to check whether the idea
              transfers to a new context.
            </p>
          )}
        </Card>
      ) : (
        <EmptyState
          title="No progress yet"
          body="Submit a solution on the Practice page and your progress will appear here."
        />
      )}

      {next && <NextStepCard recommendation={next} />}

      <section aria-label="Other concepts">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          Other concepts
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {CONCEPT_GROUPS.flatMap((g) => g.concepts)
            .filter((c) => c.concept_id !== "C3")
            .map((c) => (
              <Card key={c.concept_id} label={c.title}>
                <h3 className="text-sm font-semibold">
                  {c.concept_id} · {c.title}
                </h3>
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  Not started yet
                </p>
              </Card>
            ))}
        </div>
      </section>
    </div>
  );
}
