/** Home + progress building blocks (Step 20A).
 *
 * ContinueCard answers "what should I do next?" from the journey state;
 * NextStepCard renders one server recommendation in student language.
 * Nothing here invents learner state — every prop comes from an existing
 * backend response.
 */
import Link from "next/link";
import type { JourneyStateView, RecommendationView } from "../app/lib/api";
import {
  actionVerb,
  humanizeReason,
  isDebugMode,
  stageCopy,
} from "../app/lib/copy";
import { Card, LevelLabel, PrimaryButton } from "./ui";

export function ContinueCard({
  journeyState,
  problemTitle,
}: {
  journeyState: JourneyStateView;
  problemTitle: string | null;
}) {
  const copy = stageCopy(journeyState.stage);
  const cta =
    journeyState.stage === "transfer_done" ? "/progress" : "/practice";
  const ctaLabel =
    journeyState.stage === "transfer_done" ? "See your progress" : "Practice";
  return (
    <Card label="Continue learning">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Continue learning
      </p>
      <h2 className="mt-1 text-lg font-semibold">{copy.title}</h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
        {copy.detail}
      </p>
      {problemTitle && journeyState.stage !== "transfer_done" && (
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
          Current problem: <span className="font-medium">{problemTitle}</span>
        </p>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Link
          href={cta}
          className="rounded-lg bg-teal-800 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-700 dark:bg-teal-200 dark:text-teal-950 dark:hover:bg-teal-100"
        >
          {ctaLabel}
        </Link>
        <LevelLabel band={journeyState.band} />
      </div>
    </Card>
  );
}

export function NextStepCard({
  recommendation,
}: {
  recommendation: RecommendationView;
}) {
  return (
    <Card label="Recommended next step">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Recommended next
      </p>
      <h2 className="mt-1 text-lg font-semibold">
        {actionVerb(recommendation.action)}
      </h2>
      {recommendation.problem_title && (
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
          Suggested problem:{" "}
          <span className="font-medium">{recommendation.problem_title}</span>
        </p>
      )}
      {recommendation.reason && (
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          Why: {humanizeReason(recommendation.reason)}
        </p>
      )}
      {isDebugMode() && (
        <pre className="mt-3 overflow-x-auto rounded-md bg-zinc-100 p-3 font-mono text-xs dark:bg-zinc-900">
          {JSON.stringify(recommendation, null, 2)}
        </pre>
      )}
    </Card>
  );
}

export function FreshSessionNote({
  notice,
  onDismiss,
}: {
  notice: string;
  onDismiss: () => void;
}) {
  return (
    <Card label="Fresh session notice">
      <p className="text-sm text-zinc-600 dark:text-zinc-300">{notice}</p>
      <div className="mt-3">
        <PrimaryButton onClick={onDismiss}>Got it</PrimaryButton>
      </div>
    </Card>
  );
}
