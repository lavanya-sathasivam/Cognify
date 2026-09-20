/** Learn: the programming roadmap (Step 20A).
 *
 * Shows the eight real curriculum concepts grouped by theme. Only C3 has
 * live learner state from the existing journey endpoint; every other
 * concept honestly reports "Not started yet". No locks, streaks, XP, or
 * invented mastery anywhere.
 */
"use client";

import Link from "next/link";
import { useSession } from "../../components/session";
import { Card, LevelLabel, Loading, PageHeading } from "../../components/ui";
import { CONCEPT_GROUPS } from "../lib/concepts";

const LIVE_CONCEPT = "C3";

export default function LearnPage() {
  const { status, journey, session } = useSession();

  if (status === "loading") {
    return <Loading text="Loading the roadmap…" />;
  }

  // Journey enriches after refresh; the session payload already carries the
  // same C3 band, so fall back to it rather than flashing "not started".
  const liveBand =
    journey?.journey_state.band ?? session?.journey_state.band ?? "unknown";
  const liveStage =
    journey?.journey_state.stage ?? session?.journey_state.stage ?? "started";
  const hasLive = journey !== null || session !== null;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeading
        title="Learn Python"
        intro="Eight concepts, from first variables to recursion. Work through problems and your progress appears here — starting with loops."
      />
      {CONCEPT_GROUPS.map((group) => (
        <section key={group.group} aria-label={group.group}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            {group.group}
          </h2>
          <div className="mt-3 flex flex-col gap-4">
            {group.concepts.map((concept) => {
              const live = concept.concept_id === LIVE_CONCEPT && hasLive;
              return (
                <Card key={concept.concept_id} label={concept.title}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-base font-semibold">
                      {concept.concept_id} · {concept.title}
                    </h3>
                    {live ? (
                      <LevelLabel band={liveBand} />
                    ) : (
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">
                        Not started yet
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
                    {concept.blurb}
                  </p>
                  {live ? (
                    <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
                      {liveStage === "transfer_done"
                        ? "You completed the loop challenge — review it on the Progress page."
                        : "Currently practicing. Continue on the Practice page."}{" "}
                      <Link
                        href="/practice"
                        className="font-medium text-teal-800 underline underline-offset-2 dark:text-teal-200"
                      >
                        Practice
                      </Link>
                    </p>
                  ) : (
                    <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
                      Problems for this concept are coming — progress will
                      appear here once you can practice it.
                    </p>
                  )}
                </Card>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
