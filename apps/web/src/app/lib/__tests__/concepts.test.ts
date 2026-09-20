/** Unit tests for concept display helpers (Phase 22).
 *
 * Student UI shows human-readable concept titles and difficulty words —
 * never raw concept ids (C1…) or bare numbers.
 */
import { describe, expect, test } from "vitest";
import { conceptTitle, difficultyLabel } from "../concepts";

describe("conceptTitle", () => {
  test("maps every concept id to a human title", () => {
    expect(conceptTitle("C1")).toBe("Variables, Types, Operators, I/O");
    expect(conceptTitle("C3")).toBe("Loops & Iteration Control");
    expect(conceptTitle("C8")).toBe(
      "Recursion, Exceptions & Algorithmic Complexity Basics",
    );
  });
  test("falls back to null for missing ids", () => {
    expect(conceptTitle(null)).toBeNull();
    expect(conceptTitle(undefined)).toBeNull();
    expect(conceptTitle("C9")).toBeNull();
  });
});

describe("difficultyLabel", () => {
  test("labels difficulties without bare numbers", () => {
    for (const n of [1, 2, 3]) {
      expect(difficultyLabel(n)).not.toMatch(/[0-9]/);
      expect(difficultyLabel(n).length).toBeGreaterThan(0);
    }
    expect(difficultyLabel(1)).toBe("Getting started");
    expect(difficultyLabel(2)).toBe("Core practice");
  });
});
