/** Home: "what should I do next?" (Step 20B).
 *
 * Built from live backend data only: the session/journey state plus the
 * read-only concept overview (GET /student/concepts) and recent history
 * (GET /student/history). The adaptive engine remains the source of
 * truth — the recommendation shown here is the backend's next_action
 * (falling back to the journey recommendation), humanized by lib/copy.
 * Concept/history fetches are best-effort: if they fail, the page still
 * answers from the journey state instead of inventing content.
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "../components/session";
import { ContinueCard, FreshSessionNote, NextStepCard } from "../components/cards";
import { Card, LevelLabel, Loading, PageHeading, SecondaryButton } from "../components/ui";
import {
  api,
  type ConceptsResponse,
  type HistoryResponse,
} from "./lib/api";
import { outcomeLabel } from "./lib/copy";

export default function HomePage() {
  const {
    status,
    error,
    journey,
    session,
    sessionId,
    problem,
    freshNotice,
    dismissNotice,
    restart,
    refresh,
    chooseLanguage,
  } = useSession();
  const [concepts, setConcepts] = useState<ConceptsResponse | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);

  // Recommendations live behind GET /student/journey; concept and history
  // views enrich the answer but must never block it.
  useEffect(() => {
    if (status === "ready") {
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (status !== "ready" || !sessionId) return;
    let cancelled = false;
    api.getConcepts(sessionId).then(
      (data) => {
        if (!cancelled) setConcepts(data);
      },
      () => {
        /* best-effort: journey state still answers "what's next" */
      },
    );
    api.getHistory(sessionId, 5).then(
      (data) => {
        if (!cancelled) setHistory(data);
      },
      () => {
        /* best-effort: home works without recent activity */
      },
    );
    return () => {
      cancelled = true;
    };
  }, [status, sessionId]);

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
  const backendNext = concepts?.next_action ?? null;
  const next = backendNext
    ? {
        action: backendNext.action,
        reason: backendNext.reason,
        problem_id: backendNext.problem_id,
        problem_title: backendNext.problem_title,
      }
    : (journey?.recommendations?.[0] ?? null);
  const started = (concepts?.concepts ?? []).filter(
    (c) => c.status === "started",
  );
  const recent = history?.items?.slice(-2).reverse() ?? [];

  const trackLabel =
    (session?.language_track ?? journey?.language_track ?? problem?.language) ===
    "java"
      ? "Java"
      : "Python";
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div
        className="flex flex-wrap items-center gap-2"
        role="group"
        aria-label="Language track"
      >
        <span className="text-sm text-zinc-600 dark:text-zinc-300">
          Language:
        </span>
        {(["python", "java"] as const).map((track) => (
          <SecondaryButton
            key={track}
            onClick={() => void chooseLanguage(track)}
            className={
              trackLabel.toLowerCase() === track
                ? "border-teal-700 font-semibold"
                : undefined
            }
          >
            {track === "python" ? "Python" : "Java"}
          </SecondaryButton>
        ))}
      </div>
      <PageHeading
        title="Welcome to Cognify"
        intro={`Practice real ${trackLabel} problems. Cognify runs your code, explains what went wrong, and checks that the idea sticks in a new problem.`}
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

      {started.length > 0 && (
        <Card label="Where you stand">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Where you stand
          </p>
          <ul className="mt-2 flex flex-col gap-2">
            {started.map((c) => (
              <li
                key={c.concept_id}
                className="flex flex-wrap items-center justify-between gap-2 text-sm"
              >
                <span>
                  <span className="font-medium">
                    {c.concept_id} · {c.title}
                  </span>{" "}
                  <span className="text-zinc-500 dark:text-zinc-400">
                    · {c.attempt_count}{" "}
                    {c.attempt_count === 1 ? "attempt" : "attempts"}
                  </span>
                </span>
                <LevelLabel band={c.band} />
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
            Current level{started.length === 1 ? "" : "s"} above
            {started.some((c) => c.mastery_claim)
              ? " — a concept is mastered."
              : " — nothing mastered yet; levels grow with verified practice."}{" "}
            <Link
              href="/progress"
              className="font-medium text-teal-800 underline underline-offset-2 dark:text-teal-200"
            >
              Details
            </Link>
          </p>
        </Card>
      )}

      {recent.length > 0 && (
        <Card label="Recent activity">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Recent activity
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {recent.map((item) => (
              <li key={item.order}>
                <span className="font-medium">
                  {item.problem_title ?? "Problem"}
                </span>{" "}
                <span className="text-zinc-600 dark:text-zinc-300">
                  — {outcomeLabel(item.outcome, item.verified)}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm">
            <Link
              href="/history"
              className="font-medium text-teal-800 underline underline-offset-2 dark:text-teal-200"
            >
              Full history
            </Link>
          </p>
        </Card>
      )}
    </div>
  );
}
