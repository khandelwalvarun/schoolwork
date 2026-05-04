import { useState } from "react";
import { Assignment, PracticeKind } from "../api";
import { PracticePanel } from "./PracticePanel";

/** Heuristic: is this row a review / test / revision the parent might
 *  want to prep for? Pure pattern-match on title + body — no LLM call.
 *
 *  Cheap and deterministic; if the schoolwork-kind classifier tags
 *  this row authoritatively, future versions can read that instead of
 *  re-running the regex here. For now, keywords we've actually seen
 *  on Veracross: "review", "revision", "test", "exam", "assessment",
 *  "quiz", "unit test", "mock". Hindi-script equivalents covered too.
 */
const REVIEW_PATTERNS = [
  /\breview\b/i,
  /\brevision\b/i,
  /\btest\b/i,
  /\bexam\b/i,
  /\bassessment\b/i,
  /\bquiz\b/i,
  /\bmock\b/i,
  /\bmid[- ]?term\b/i,
  /\bunit\s*\d+\b/i,
  /पुनरावृत्ति|परीक्षा|प्रश्नोत्तरी/,  // Hindi: revision, exam, quiz
];

export function isReviewLike(a: Pick<Assignment, "title" | "title_en" | "body" | "notes_en" | "tags">): boolean {
  if (a.tags && (a.tags.includes("revision") || a.tags.includes("re-do"))) {
    return true;
  }
  const blob = [a.title, a.title_en, a.body, a.notes_en]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return REVIEW_PATTERNS.some((re) => re.test(blob));
}

/** Two entry points side-by-side on every assignment row:
 *
 *    📝 prep  — only for review-like rows (test/quiz/revision/etc.)
 *    💡 help  — for every assignment, no matter the kind
 *
 *  Both open the same PracticePanel; the `kind` prop selects the LLM
 *  prompt + output schema. Iterating in either flavour stays in that
 *  flavour; switching kinds means a new session for the same row.
 */
export function ReviewPracticeButton({
  a,
  className,
}: {
  a: Assignment;
  className?: string;
}) {
  const [openKind, setOpenKind] = useState<PracticeKind | null>(null);
  const isReview = isReviewLike(a);
  // Show prep button only for review-like rows; show help button for
  // every assignment (incl. review rows — sometimes you want help, not
  // a separate practice sheet).
  const onlyForAssignments = a.kind === "assignment" || a.kind === undefined;
  if (!onlyForAssignments) return null;

  return (
    <>
      {isReview && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpenKind("review_prep");
          }}
          className={
            (className ?? "") +
            " shrink-0 inline-flex items-center gap-0.5 text-[11px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-800 border border-purple-200 hover:bg-purple-200"
          }
          title="Generate or open practice prep for this review"
          aria-label="Open practice prep"
        >
          📝 prep
        </button>
      )}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpenKind("assignment_help");
        }}
        className={
          (className ?? "") +
          " shrink-0 inline-flex items-center gap-0.5 text-[11px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200 hover:bg-amber-200"
        }
        title="Get LLM help on this assignment (outline / hints / worked example)"
        aria-label="Open assignment help"
      >
        💡 help
      </button>
      {openKind && (
        <PracticePanel
          childId={a.child_id}
          subject={a.subject || "Subject"}
          linkedAssignment={a}
          topic={a.syllabus_context || null}
          kind={openKind}
          onClose={() => setOpenKind(null)}
        />
      )}
    </>
  );
}
