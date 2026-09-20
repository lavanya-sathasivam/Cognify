/** Learn: the programming roadmap (Step 20B).
 *
 * Real learner state from GET /student/concepts for all eight concepts,
 * grouped by the backend's presentation groups (taxonomy owns titles and
 * prerequisites; grouping is display structure only). Concepts with zero
 * attempts honestly report "Not started yet" — no progress is invented.
 * Internal codes are never rendered (see lib/copy).
 */
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSession } from "../../components/session";
import {
  Alert,
  Badge,
  Card,
  LevelLabel,
  Loading,
  PageHeading,
  SecondaryButton,
} from "../../components/ui";
import { api, friendlyError, type ConceptsResponse } from "../lib/api";
import {
  hintRelianceCopy,
  masteryMeaning,
  transferCopy,
  trendLabel,
  trendSentence,
} from "../lib/copy";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: ConceptsResponse }
  | { kind: "failed"; error: string };

export default function LearnPage() {
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
    return <Loading text="Loading the roadmap…" />;
  }

  const trackLabel =
    state.kind === "ready" && state.data.language_track === "java"
      ? "Java"
      : "Python";
  if (state.kind === "failed") {
    return (
      <div className="flex max-w-3xl flex-col gap-6">
        <PageHeading
          title={`Learn ${trackLabel}`}
          intro="Eight concepts, from first variables to recursion."
        />
        <Alert title="Couldn't load the roadmap.">
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

  // Group concepts in backend order (first appearance of each group).
  const groups: { group: string; ids: string[] }[] = [];
  const byId = new Map(state.data.concepts.map((c) => [c.concept_id, c]));
  for (const concept of state.data.concepts) {
    const existing = groups.find((g) => g.group === concept.group);
    if (existing) existing.ids.push(concept.concept_id);
    else groups.push({ group: concept.group, ids: [concept.concept_id] });
  }
  const recommendedId = state.data.next_action?.concept_id ?? null;
  const titleOf = (id: string) => byId.get(id)?.title ?? "an earlier concept";

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeading
        title={`Learn ${trackLabel}`}
        intro="Eight concepts, from first variables to recursion. Work through problems and your progress appears here."
      />
      {groups.map((group) => (
        <section key={group.group} aria-label={group.group}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            {group.group}
          </h2>
          <div className="mt-3 flex flex-col gap-4">
            {group.ids.map((id) => {
              const concept = byId.get(id);
              if (!concept) return null;
              const started = concept.status === "started";
              const recent = concept.recent_history.slice(-3);
              const passed = recent.filter((r) => r.passed).length;
              const recommended = recommendedId === concept.concept_id;
              return (
                <Card key={concept.concept_id} label={concept.title}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-base font-semibold">{concept.title}</h3>
                    <span className="flex flex-wrap items-center gap-2">
                      {recommended && (
                        <Badge tone="info">Recommended next</Badge>
                      )}
                      {started ? (
                        <LevelLabel band={concept.band} />
                      ) : (
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          Not started yet
                        </span>
                      )}
                    </span>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                    {concept.description}
                  </p>
                  {concept.prerequisites.length > 0 && (
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      Builds on:{" "}
                      {concept.prerequisites.map(titleOf).join(" · ")}
                    </p>
                  )}
                  {started ? (
                    <div className="mt-2 flex flex-col gap-1 text-sm text-zinc-600 dark:text-zinc-300">
                      <p>
                        {concept.attempt_count}{" "}
                        {concept.attempt_count === 1 ? "attempt" : "attempts"} ·{" "}
                        {trendLabel(concept.trend)}
                        {recent.length > 0 &&
                          ` · ${passed} of ${recent.length} recent correct`}
                      </p>
                      {masteryMeaning(concept.band) && (
                        <p>{masteryMeaning(concept.band)}</p>
                      )}
                      {trendSentence(concept.trend) && (
                        <p>{trendSentence(concept.trend)}</p>
                      )}
                      <p>
                        {transferCopy(
                          concept.transfer.attempts,
                          concept.transfer.successes,
                        )}
                      </p>
                      <p>
                        {hintRelianceCopy(
                          concept.hint_dependence,
                          concept.hint_count,
                        )}
                      </p>
                      {concept.active_misconception_count > 0 ? (
                        <p>
                          {concept.active_misconception_count}{" "}
                          {concept.active_misconception_count === 1
                            ? "area needs"
                            : "areas need"}{" "}
                          more practice — follow your recommended next step.
                        </p>
                      ) : (
                        <p>No active weak areas right now.</p>
                      )}
                      <p>
                        <Link
                          href="/practice"
                          className="font-medium text-teal-800 underline underline-offset-2 dark:text-teal-200"
                        >
                          Practice
                        </Link>{" "}
                        <span aria-hidden="true">·</span>{" "}
                        <Link
                          href="/progress"
                          className="font-medium text-teal-800 underline underline-offset-2 dark:text-teal-200"
                        >
                          Progress
                        </Link>
                      </p>
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
                      No attempts yet — your progress will appear here once you
                      practice this concept.
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
