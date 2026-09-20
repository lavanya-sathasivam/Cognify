/** Student-facing copy (Step 20A).
 *
 * The backend speaks in internal codes (misconception IDs, adaptive action
 * types, intervention types). Students must never see those codes in normal
 * UI. This module is the single place that translates internal values into
 * natural language. Raw values remain available only through the debug
 * mechanism (`?debug=1`, see `isDebugMode`).
 */

const ACTION_VERBS: Record<string, string> = {
  REVIEW_CONCEPT: "Review this concept before trying another problem.",
  REMEDIAL_PROBLEM: "Practice a simpler variant of this idea first.",
  PRACTICE_PROBLEM: "Keep practicing this concept to make it stick.",
  CHALLENGE_PROBLEM: "Stretch yourself with a harder problem.",
  TRANSFER_PROBLEM: "Try a related problem to check the idea transfers.",
  REVIEW_PREREQUISITE: "Strengthen a foundation first — it will unblock this.",
};

const LEVEL_LABELS: Record<string, string> = {
  novice: "Starting out",
  emerging: "Developing",
  proficient: "Solid",
  mastered: "Strong",
  unknown: "Not started yet",
};

const STAGE_COPY: Record<string, { title: string; detail: string }> = {
  started: {
    title: "Start your first problem",
    detail: "Work through the problem below and submit your code.",
  },
  practicing: {
    title: "Keep working on the problem",
    detail: "Read the feedback, adjust your code, and submit again.",
  },
  retry_passed: {
    title: "Try the related problem",
    detail: "You solved it — now check the idea holds in a new context.",
  },
  transfer_done: {
    title: "Review what you learned",
    detail: "See your progress and what to practice next.",
  },
};

/** Matches backend misconception IDs such as C3-M01 or C1-M02. */
const MISCONCEPTION_RE = /\bC[1-8]-M\d{2}\b/g;

/** Matches SCREAMING_SNAKE internal codes (R3, REVIEW_CONCEPT, ...). */
const CODE_TOKEN_RE = /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g;

export function actionVerb(action: string | null): string {
  if (!action) return "See the recommended next step below.";
  return ACTION_VERBS[action] ?? "See the recommended next step below.";
}

export function levelLabel(band: string | null | undefined): string {
  if (!band) return LEVEL_LABELS.unknown;
  return LEVEL_LABELS[band] ?? LEVEL_LABELS.unknown;
}

export function stageCopy(stage: string): { title: string; detail: string } {
  return (
    STAGE_COPY[stage] ?? {
      title: "Continue learning",
      detail: "Pick up where you left off.",
    }
  );
}

/** Remove internal codes from a server-provided sentence for display. */
export function stripCodes(text: string): string {
  return text
    .replace(MISCONCEPTION_RE, "this idea")
    .replace(CODE_TOKEN_RE, "this step")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/**
 * Rewrite a server recommendation reason into student language.
 * Keeps the server's meaning; drops codes and recurring-weakness jargon.
 */
export function humanizeReason(reason: string | null): string {
  if (!reason || !reason.trim()) return "Based on your recent attempts.";
  let text = reason.trim();
  // "Recurring weakness C3-M01 in C3 (3 recent, 4 total): ..." ->
  // "You've made a similar mistake across a few problems. ..."
  text = text.replace(
    /recurring weakness\s+C[1-8]-M\d{2}\s+in\s+C[1-8]\s*\([^)]*\)\s*:?\s*/i,
    "You've made a similar mistake across a few problems. ",
  );
  text = stripCodes(text);
  return text || "Based on your recent attempts.";
}

/** True when the URL carries ?debug=1 (developer view of raw values). */
export function isDebugMode(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  } catch {
    return false;
  }
}

/** Test helper: does this string contain anything a student must not see? */
export function hasInternalCodes(text: string): boolean {
  MISCONCEPTION_RE.lastIndex = 0;
  CODE_TOKEN_RE.lastIndex = 0;
  return MISCONCEPTION_RE.test(text) || CODE_TOKEN_RE.test(text);
}
