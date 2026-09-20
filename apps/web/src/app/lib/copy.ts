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

const TREND_LABELS: Record<string, string> = {
  unknown: "No trend yet",
  stable: "Steady",
  improving: "Improving",
  declining: "Needs attention",
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

/** Matches raw decimals (mastery floats, thresholds, ratios): never student-facing. */
const FLOAT_RE = /\b\d+\.\d+\b/;

/** Matches lone concept IDs (C1..C8) that survived template rewrites. */
const LONE_CONCEPT_RE = /\bC[1-8]\b/g;

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
 * Keeps the server's meaning; drops codes, concept IDs, mastery floats,
 * thresholds, and recurring-weakness jargon.
 *
 * Covers every adaptive reason template (packages/adaptive/reasons.py):
 * prerequisite, low mastery, recurring weakness, emerging, proficient,
 * transfer-ready, challenge-ready, declining trend, and hint dependence.
 * A generic residue pass catches anything unexpected so raw engine values
 * can never reach the student UI.
 */
export function humanizeReason(reason: string | null): string {
  if (!reason || !reason.trim()) return "Based on your recent attempts.";
  let text = ` ${reason.trim()}`;
  // "Recurring weakness C3-M01 in C3 (2 recent, 3 total): ..." ->
  // "You've made a similar mistake across a few problems. ..."
  text = text.replace(
    /recurring weakness\s+C[1-8]-M\d{2}\s+in\s+C[1-8]\s*\([^)]*\)\s*:?\s*/i,
    " You've made a similar mistake across a few problems. ",
  );
  // Declining tail wraps another reason ("... Trend is declining for C3,
  // so review is urgent."): humanize the tail first so the base reason
  // below still gets its own rewrite.
  text = text.replace(
    /\s*trend is declining for C[1-8],?\s+so review is urgent\.?/i,
    " Your recent performance has dipped — a review may help.",
  );
  // "Prerequisite C1 mastery is 0.20, below the required 0.60, so review
  // C1 before advancing to C2."
  text = text.replace(
    /prerequisite\s+C[1-8]\s+mastery is \d+\.\d+,?\s+below the required \d+\.\d+,?\s+so review C[1-8] before advancing to C[1-8]\.?/i,
    " A foundation needs strengthening before the next idea unlocks.",
  );
  // "C3 mastery is 0.12, below 0.40: ..."
  text = text.replace(
    /C[1-8]\s+mastery is \d+\.\d+,?\s+below [\d.]+:?\s*/i,
    " Your mastery is still building. ",
  );
  // "C3 mastery is 0.38 (emerging): ..."
  text = text.replace(
    /C[1-8]\s+mastery is \d+\.\d+\s*\(emerging\):?\s*/i,
    " You're making progress. ",
  );
  // "C3 mastery is 0.62 (proficient): ..."
  text = text.replace(
    /C[1-8]\s+mastery is \d+\.\d+\s*\(proficient\):?\s*/i,
    " You're getting consistent. ",
  );
  // "C3 mastery is 0.71 with transfer success 0.50: ..."
  text = text.replace(
    /C[1-8]\s+mastery is \d+\.\d+\s+with transfer success [\d.]+:?\s*/i,
    " You're ready to verify this idea. ",
  );
  // "C3 mastery is 0.85 (mastered): ..." (only fires when the backend
  // actually reports mastery, so the claim stays backend-supported).
  text = text.replace(
    /C[1-8]\s+mastery is \d+\.\d+\s*\(mastered\):?\s*/i,
    " You've shown strong understanding. ",
  );
  // "Hint dependence is 0.67 for C3: ..."
  text = text.replace(
    /hint dependence is \d+\.\d+\s+for C[1-8]:?\s*/i,
    " You've been relying on hints. ",
  );
  text = stripCodes(text);
  // Generic residue: lone concept IDs, floats, and thresholds that no
  // template rule consumed (e.g. future engine wording).
  text = text
    .replace(LONE_CONCEPT_RE, "this concept")
    .replace(/mastery is \d+\.\d+/gi, "progress is building")
    .replace(/below the required \d+\.\d+/gi, "below the required level")
    .replace(/below \d+\.\d+/gi, "below the target level")
    .replace(/transfer success \d+\.\d+/gi, "transfer results")
    .replace(/hint dependence is \d+\.\d+/gi, "hint use is frequent")
    .replace(/\s{2,}/g, " ")
    .trim();
  // Capitalize sentence starts left lowercase by the rewrites above.
  text = text.replace(/(^|[.!?]\s+)([a-z])/g, (_, p: string, c: string) => p + c.toUpperCase());
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

/** Human label for a backend mastery trend. Never shows raw values. */
export function trendLabel(trend: string | null | undefined): string {
  if (!trend) return TREND_LABELS.unknown;
  return TREND_LABELS[trend] ?? TREND_LABELS.unknown;
}

/** Full-sentence trend explanation, or null when there is no trend yet.
 *
 * "unknown" honestly yields nothing — the UI must omit the trend rather
 * than invent one.
 */
export function trendSentence(trend: string | null | undefined): string | null {
  if (trend === "improving") return "Your recent performance is improving.";
  if (trend === "declining")
    return "Your recent performance has dipped. A review may help.";
  if (trend === "stable") return "Your recent performance is stable.";
  return null;
}

/** What the student's current band means, or null before any attempt.
 *
 * "mastered" is only ever rendered for the backend's mastered band, so a
 * "Strong understanding" claim stays backend-supported.
 */
export function masteryMeaning(
  band: string | null | undefined,
): string | null {
  if (band === "novice") return "Getting started — early attempts on this concept.";
  if (band === "emerging")
    return "Building confidence — keep practicing for consistency.";
  if (band === "proficient")
    return "Developing consistency — nearly strong.";
  if (band === "mastered") return "Strong understanding.";
  return null;
}

/** Human sentence for hint reliance (Step 20B progress view). */
export function hintRelianceCopy(hintDependence: number, hintCount: number): string {
  if (!hintCount || hintDependence <= 0) return "Working independently, no hints used.";
  if (hintDependence >= 0.5)
    return "Relying on hints — try the next problem without one.";
  return "Mostly independent, with an occasional hint.";
}

/** Human sentence for transfer performance (Step 20B progress view). */
export function transferCopy(attempts: number, successes: number): string {
  if (!attempts) return "No transfer attempts yet — solve the original first.";
  if (successes >= attempts)
    return `Transfer solid: ${successes} of ${attempts} correct in new contexts.`;
  return `Transfer in progress: ${successes} of ${attempts} correct in new contexts.`;
}

/** Human result words for one history entry (never raw codes). */
export function outcomeLabel(outcome: string, verified: boolean): string {
  if (outcome === "passed") {
    return verified ? "Solved — improvement verified" : "Solved";
  }
  return "Needs another attempt";
}

/** Test helper: does this string contain anything a student must not see?
 *
 * Covers misconception IDs, SCREAMING_SNAKE codes, lone concept IDs, and
 * raw decimals (mastery floats, thresholds, ratios).
 */
export function hasInternalCodes(text: string): boolean {
  MISCONCEPTION_RE.lastIndex = 0;
  CODE_TOKEN_RE.lastIndex = 0;
  FLOAT_RE.lastIndex = 0;
  LONE_CONCEPT_RE.lastIndex = 0;
  return (
    MISCONCEPTION_RE.test(text) ||
    CODE_TOKEN_RE.test(text) ||
    FLOAT_RE.test(text) ||
    LONE_CONCEPT_RE.test(text)
  );
}
