/** Static curriculum metadata (Step 20A).
 *
 * The eight Cognify concepts, grouped the way a student meets them. This is
 * curriculum structure (names and groupings from the shared taxonomy), not
 * learner state: no mastery, progress, locks, streaks, or badges live here.
 * Per-concept learner state arrives only from backend endpoints (Step 20B).
 */

export interface ConceptMeta {
  concept_id: string;
  title: string;
  blurb: string;
}

export interface ConceptGroup {
  group: string;
  concepts: ConceptMeta[];
}

export const CONCEPT_GROUPS: ConceptGroup[] = [
  {
    group: "Foundations",
    concepts: [
      {
        concept_id: "C1",
        title: "Variables, Types, Operators, I/O",
        blurb: "Storing values, converting types, and reading input.",
      },
    ],
  },
  {
    group: "Control Flow",
    concepts: [
      {
        concept_id: "C2",
        title: "Conditionals & Boolean Logic",
        blurb: "Making decisions with if/else and boolean expressions.",
      },
      {
        concept_id: "C3",
        title: "Loops & Iteration Control",
        blurb: "Repeating work with loops that start and stop correctly.",
      },
    ],
  },
  {
    group: "Functions",
    concepts: [
      {
        concept_id: "C4",
        title: "Functions / Methods, Parameters, Scope & Return",
        blurb: "Packaging logic into reusable, well-scoped functions.",
      },
    ],
  },
  {
    group: "Collections",
    concepts: [
      {
        concept_id: "C5",
        title: "Lists / Arrays & Strings",
        blurb: "Working with ordered sequences of items and text.",
      },
      {
        concept_id: "C6",
        title: "Dictionaries / Maps, Sets & Nested Structures",
        blurb: "Looking things up by key and organizing data.",
      },
    ],
  },
  {
    group: "Objects",
    concepts: [
      {
        concept_id: "C7",
        title: "OOP: Classes, Objects, Encapsulation, Inheritance",
        blurb: "Modeling ideas with classes and their own state.",
      },
    ],
  },
  {
    group: "Recursion & Beyond",
    concepts: [
      {
        concept_id: "C8",
        title: "Recursion, Exceptions & Algorithmic Complexity Basics",
        blurb: "Solving problems by breaking them into smaller pieces.",
      },
    ],
  },
];

export const ALL_CONCEPTS: ConceptMeta[] = CONCEPT_GROUPS.flatMap(
  (g) => g.concepts,
);

/** Human-readable concept title for a concept id (student UI never shows raw ids). */
export function conceptTitle(conceptId: string | null | undefined): string | null {
  if (!conceptId) return null;
  return ALL_CONCEPTS.find((c) => c.concept_id === conceptId)?.title ?? null;
}

/** Student-friendly difficulty wording (raw numbers stay out of normal UI). */
export function difficultyLabel(difficulty: number): string {
  if (difficulty <= 1) return "Getting started";
  if (difficulty === 2) return "Core practice";
  return "Stretch";
}
