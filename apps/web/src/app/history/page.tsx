/** History: visible memory of learning (Step 20A foundation).
 *
 * The existing student API exposes no attempt-history endpoint, so this
 * page honestly reports that learning history will appear here once
 * backend support lands (Step 20B). No history is invented.
 */
"use client";

import Link from "next/link";
import { EmptyState, PageHeading } from "../../components/ui";

export default function HistoryPage() {
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeading
        title="Your history"
        intro="Every attempt, mistake found, and improvement verified — Cognify's memory of your learning, made visible."
      />
      <EmptyState
        title="No learning history yet"
        body="Detailed history — problems attempted, misconceptions found, interventions received, and transfer results — will appear here once backend history support is added. Your current session's progress is still tracked and shown on the Progress page."
        action={
          <Link
            href="/practice"
            className="rounded-lg bg-teal-800 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-700 dark:bg-teal-200 dark:text-teal-950 dark:hover:bg-teal-100"
          >
            Practice now
          </Link>
        }
      />
    </div>
  );
}
