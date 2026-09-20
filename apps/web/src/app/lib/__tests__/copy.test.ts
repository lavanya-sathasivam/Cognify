/** Unit tests for the student copy layer (Step 20A).
 *
 * Pure functions: every adaptive action and mastery band must map to
 * natural language, and no internal code may survive humanization.
 */
import { describe, expect, test } from "vitest";
import {
  actionVerb,
  hasInternalCodes,
  humanizeReason,
  levelLabel,
  stageCopy,
  stripCodes,
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

describe("stripCodes and hasInternalCodes", () => {
  test("detects misconception and action codes", () => {
    expect(hasInternalCodes("See C3-M01")).toBe(true);
    expect(hasInternalCodes("Do REVIEW_CONCEPT now")).toBe(true);
    expect(hasInternalCodes("Check the boundary of your loop.")).toBe(false);
  });
  test("stripCodes removes codes", () => {
    expect(hasInternalCodes(stripCodes("Fix C3-M01 then REVIEW_CONCEPT"))).toBe(
      false,
    );
  });
});
