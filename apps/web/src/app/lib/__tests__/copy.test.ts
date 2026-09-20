/** Unit tests for the student copy layer (Step 20A).
 *
 * Pure functions: every adaptive action and mastery band must map to
 * natural language, and no internal code may survive humanization.
 */
import { describe, expect, test } from "vitest";
import {
  actionVerb,
  hasInternalCodes,
  hintRelianceCopy,
  humanizeReason,
  levelLabel,
  masteryMeaning,
  outcomeLabel,
  stageCopy,
  stripCodes,
  transferCopy,
  trendSentence,
} from "../copy";

describe("actionVerb", () => {
  const actions = [
    "REVIEW_CONCEPT",
    "REMEDIAL_PROBLEM",
    "PRACTICE_PROBLEM",
    "CHALLENGE_PROBLEM",
    "TRANSFER_PROBLEM",
    "REVIEW_PREREQUISITE",
  ];
  for (const action of actions) {
    test(`maps ${action} to student language without codes`, () => {
      const text = actionVerb(action);
      expect(text.length).toBeGreaterThan(0);
      expect(hasInternalCodes(text)).toBe(false);
    });
  }
  test("falls back for null and unknown actions", () => {
    expect(hasInternalCodes(actionVerb(null))).toBe(false);
    expect(hasInternalCodes(actionVerb("SOMETHING_NEW"))).toBe(false);
  });
});

describe("levelLabel", () => {
  test("labels every known band without numbers", () => {
    expect(levelLabel("novice")).toBe("Starting out");
    expect(levelLabel("emerging")).toBe("Developing");
    expect(levelLabel("proficient")).toBe("Solid");
    expect(levelLabel("mastered")).toBe("Strong");
    expect(levelLabel("unknown")).toBe("Not started yet");
  });
  test("never exposes raw mastery values", () => {
    for (const band of ["novice", "emerging", "proficient", "mastered"]) {
      expect(levelLabel(band)).not.toMatch(/[0-9]/);
    }
  });
});

describe("stageCopy", () => {
  test("covers every journey stage", () => {
    for (const stage of ["started", "practicing", "retry_passed", "transfer_done"]) {
      const copy = stageCopy(stage);
      expect(copy.title.length).toBeGreaterThan(0);
      expect(copy.detail.length).toBeGreaterThan(0);
    }
  });
});

describe("humanizeReason", () => {
  test("rewrites recurring-weakness jargon without codes", () => {
    const out = humanizeReason(
      "Recurring weakness C3-M01 in C3 (2 recent, 3 total): practice loop bounds.",
    );
    expect(out).toMatch(/similar mistake/);
    expect(hasInternalCodes(out)).toBe(false);
  });
  test("strips stray codes from plain reasons", () => {
    const out = humanizeReason("REVIEW_CONCEPT needed for C3-M05 before TRANSFER_PROBLEM.");
    expect(hasInternalCodes(out)).toBe(false);
  });
  test("falls back on empty input", () => {
    expect(humanizeReason(null)).toBe("Based on your recent attempts.");
    expect(humanizeReason("   ")).toBe("Based on your recent attempts.");
  });
});

describe("humanizeReason adaptive templates", () => {
  // Real engine strings (packages/adaptive/reasons.py, probed live).
  const templates = [
    "Prerequisite C1 mastery is 0.20, below the required 0.60, so review C1 before advancing to C2.",
    "C3 mastery is 0.12, below 0.40: review the concept and attempt targeted remedial practice.",
    "C3 mastery is 0.45 (emerging): additional practice is appropriate to consolidate the concept.",
    "C3 mastery is 0.62 (proficient): practice to consolidate, with transfer when readiness evidence is sufficient.",
    "C3 mastery is 0.71 with transfer success 0.50: attempt an isomorphic transfer variant to verify generalization.",
    "C3 mastery is 0.85 (mastered): attempt a challenge problem to extend the concept.",
    "C3 mastery is 0.55 (proficient): practice to consolidate. Trend is declining for C3, so review is urgent.",
    "Hint dependence is 0.67 for C3: prefer concept review or easier targeted practice over harder problems.",
  ];
  for (const reason of templates) {
    test(`humanizes without engine values: ${reason.slice(0, 40)}…`, () => {
      const out = humanizeReason(reason);
      expect(out.length).toBeGreaterThan(0);
      expect(hasInternalCodes(out)).toBe(false);
      expect(out).not.toMatch(/\d+\.\d+/);
      expect(out).not.toMatch(/\bC[1-8]\b/);
    });
  }
  test("prerequisite keeps the foundation meaning", () => {
    expect(humanizeReason(templates[0])).toMatch(/foundation/i);
  });
  test("low mastery keeps the keep-practicing meaning", () => {
    expect(humanizeReason(templates[1])).toMatch(/still building/i);
  });
  test("declining keeps the dip meaning", () => {
    expect(humanizeReason(templates[6])).toMatch(/dipped/i);
  });
  test("hint dependence stays kind, never shaming", () => {
    const out = humanizeReason(templates[7]);
    expect(out).toMatch(/hint/i);
    expect(out).not.toMatch(/shame|lazy|bad student/i);
  });
});

describe("trendSentence", () => {
  test("explains known trends in student language", () => {
    expect(trendSentence("improving")).toBe(
      "Your recent performance is improving.",
    );
    expect(trendSentence("declining")).toBe(
      "Your recent performance has dipped. A review may help.",
    );
    expect(trendSentence("stable")).toBe("Your recent performance is stable.");
  });
  test("invents nothing for unknown trends", () => {
    expect(trendSentence("unknown")).toBeNull();
    expect(trendSentence(null)).toBeNull();
    expect(trendSentence("bogus")).toBeNull();
  });
});

describe("masteryMeaning", () => {
  test("explains every band without numbers", () => {
    for (const band of ["novice", "emerging", "proficient", "mastered"]) {
      const meaning = masteryMeaning(band);
      expect(meaning).not.toBeNull();
      expect(meaning).not.toMatch(/[0-9]/);
      expect(hasInternalCodes(meaning!)).toBe(false);
    }
    expect(masteryMeaning("mastered")).toMatch(/Strong understanding/);
  });
  test("claims nothing before any attempt", () => {
    expect(masteryMeaning("unknown")).toBeNull();
    expect(masteryMeaning(null)).toBeNull();
  });
});

describe("stripCodes and hasInternalCodes", () => {
  test("detects misconception and action codes", () => {
    expect(hasInternalCodes("See C3-M01")).toBe(true);
    expect(hasInternalCodes("Do REVIEW_CONCEPT now")).toBe(true);
    expect(hasInternalCodes("Check the boundary of your loop.")).toBe(false);
  });
  test("detects raw engine values: floats and lone concept IDs", () => {
    expect(hasInternalCodes("C3 mastery is 0.12")).toBe(true);
    expect(hasInternalCodes("below the required 0.60")).toBe(true);
    expect(hasInternalCodes("review C1 before C2")).toBe(true);
    expect(hasInternalCodes("You passed 2 of 5 tests.")).toBe(false);
  });
  test("stripCodes removes codes", () => {
    expect(hasInternalCodes(stripCodes("Fix C3-M01 then REVIEW_CONCEPT"))).toBe(
      false,
    );
  });
});

describe("progress helpers", () => {
  test("hintRelianceCopy is kind and code-free", () => {
    for (const text of [
      hintRelianceCopy(0, 0),
      hintRelianceCopy(0.8, 4),
      hintRelianceCopy(0.2, 1),
    ]) {
      expect(hasInternalCodes(text)).toBe(false);
    }
    expect(hintRelianceCopy(0.8, 4)).toMatch(/hint/i);
    expect(hintRelianceCopy(0, 0)).toMatch(/independent/i);
  });
  test("transferCopy explains new-context performance", () => {
    expect(transferCopy(0, 0)).toMatch(/No transfer attempts yet/);
    expect(transferCopy(2, 2)).toMatch(/Transfer solid/);
    expect(transferCopy(2, 1)).toMatch(/in progress/);
    expect(hasInternalCodes(transferCopy(2, 1))).toBe(false);
  });
  test("outcomeLabel never leaks raw outcomes", () => {
    expect(outcomeLabel("passed", true)).toMatch(/verified/i);
    expect(outcomeLabel("passed", false)).toBe("Solved");
    expect(outcomeLabel("failed", false)).toBe("Needs another attempt");
  });
});
