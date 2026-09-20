/** History: visible memory of learning (Step 20B).
 *
 * Real attempt history from GET /student/history: what was attempted,
 * what happened, and whether improvement was verified — in plain
 * language, never raw codes. Honest loading, error, and empty states;
 * failures offer a way back to Practice rather than invented content.
 */
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSession } from "../../components/session";
import {
  Alert,
  Card,
  EmptyState,
  Loading,
  Mark,
  PageHeading,
  SecondaryButton,
} from "../../components/ui";
import { api, friendlyError, type HistoryResponse } from "../lib/api";
import { outcomeLabel, stripCodes } from "../lib/copy";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: HistoryResponse }
  | { kind: "failed"; error: string };

function load(
  sessionId: string,
  setState: (s: LoadState) => void,
  cancelled: { current: boolean },
) {
  api
    .getHistory(sessionId)
    .then((data) => {
      if (!cancelled.current) setState({ kind: "ready", data });
    })
    .catch((err: unknown) => {
      if (!cancelled.current)
        setState({ kind: "failed", error: friendlyError(err) });
    });
}

export default function HistoryPage() {
  const { status, sessionId } = useSession();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    if (status !== "ready" || !sessionId) return;
    const cancelled = { current: false };
    // Initial state is already "loading"; async completions in load() are
    // the only in-effect state updates (no synchronous reset).
    load(sessionId, setState, cancelled);
    return () => {
      cancelled.current = true;
    };
  }, [status, sessionId]);

  if (status === "loading" || state.kind === "loading") {
    return <Loading text="Loading your history…" />;
  }

  if (state.kind === "failed") {
    return (
      <div className="flex max-w-3xl flex-col gap-6">
        <PageHeading
          title="Your history"
          intro="Every attempt, mistake found, and improvement verified — Cognify's memory of your learning, made visible."
        />
        <Alert title="Couldn't load your history.">
          <p>{state.error}</p>
          <div className="mt-3">
            <SecondaryButton
              onClick={() => {
                if (!sessionId) return;
                setState({ kind: "loading" });
                load(sessionId, setState, { current: false });
              }}
            >
              Try again
            </SecondaryButton>
          </div>
        </Alert>
      </div>
    );
  }

  const items = state.data.items;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeading
        title="Your history"
        intro="Every attempt, mistake found, and improvement verified — Cognify's memory of your learning, made visible."
      />
      {items.length === 0 ? (
        <EmptyState
          title="No learning history yet"
          body="Submit a solution on the Practice page and each attempt will appear here with what happened and what to try next."
          action={
            <Link
              href="/practice"
              className="rounded-lg bg-teal-800 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-700 dark:bg-teal-200 dark:text-teal-950 dark:hover:bg-teal-100"
            >
              Practice now
            </Link>
          }
        />
      ) : (
        <ol className="flex flex-col gap-4">
          {items.map((item) => (
            <li key={item.order}>
              <Card
                label={item.problem_title ?? item.problem_id ?? "Attempt"}
              >
                <div className="flex items-start gap-3">
                  <Mark kind={item.outcome === "passed" ? "pass" : "fail"} />
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold">
                      {item.problem_title ?? "Problem"}{" "}
                      <span className="font-normal text-zinc-500 dark:text-zinc-400">
                        · {item.concept_title ?? item.concept_id}
                        {item.is_transfer ? " · new context" : ""}
                      </span>
                    </h2>
                    <p className="mt-1 text-sm font-medium">
                      {outcomeLabel(item.outcome, item.verified)}
                    </p>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
                      {stripCodes(item.feedback)}
                    </p>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
