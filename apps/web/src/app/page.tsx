/** Home: "what should I do next?" (Step 20A).
 *
 * Built only from existing endpoints (session + journey). Shows the live
 * C3 journey state and the stored next recommendation. No progress is
 * fabricated for other concepts.
 */
"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useSession } from "../components/session";
import { ContinueCard, FreshSessionNote, NextStepCard } from "../components/cards";
import { Card, Loading, PageHeading, SecondaryButton } from "../components/ui";

export default function HomePage() {
  const {
    status,
    error,
    journey,
    session,
    problem,
    freshNotice,
    dismissNotice,
    restart,
    refresh,
  } = useSession();

  // Recommendations live behind GET /student/journey; load them once the
  // session is ready (the session payload alone carries no recommendations).
  useEffect(() => {
    if (status === "ready") {
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  if (status === "loading") {
    return <Loading text="Loading your learning state…" />;
  }

  if (status === "failed") {
    return (
      <div className="flex max-w-2xl flex-col gap-4">
        <PageHeading title="Welcome to Cognify" />
        <Card label="Session error">
          <p className="font-medium">Couldn&apos;t start your session.</p>
          <p className="mt-1 text-sm">{error ?? "Backend unreachable."}</p>
          <div className="mt-3">
            <SecondaryButton onClick={() => void restart()}>
              Try again
            </SecondaryButton>
          </div>
        </Card>
      </div>
    );
  }

  const journeyState =
    journey?.journey_state ?? session?.journey_state ?? null;
  const next = journey?.recommendations?.[0] ?? null;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeading
        title="Welcome to Cognify"
        intro="Practice real Python problems. Cognify runs your code, explains what went wrong, and checks that the idea sticks in a new problem."
      />

      {freshNotice && (
        <FreshSessionNote notice={freshNotice} onDismiss={dismissNotice} />
      )}

      {journeyState ? (
        <ContinueCard
          journeyState={journeyState}
          problemTitle={problem?.title ?? null}
        />
      ) : (
        <Card label="Continue learning">
          <p className="text-sm text-zinc-600 dark:text-zinc-300">
            Your session is ready — head to Practice to begin.
          </p>
          <div className="mt-3">
            <Link
              href="/practice"
              className="rounded-lg bg-teal-800 px-4 py-2 text-sm font-medium text-white dark:bg-teal-200 dark:text-teal-950"
            >
              Practice
            </Link>
          </div>
        </Card>
      )}

      {next ? (
        <NextStepCard recommendation={next} />
      ) : (
        <Card label="Recommended next">
          <h2 className="text-base font-semibold">No recommendation yet</h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
            Submit a solution on the Practice page and Cognify will suggest
            what to do next based on how it went.
          </p>
        </Card>
      )}
    </div>
  );
}
