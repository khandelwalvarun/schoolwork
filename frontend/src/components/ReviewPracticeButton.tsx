import { useState } from "react";
import { Assignment, PracticeKind } from "../api";
import { PracticePanel } from "./PracticePanel";

/** Heuristic: is this row a review / test / revision? Pure pattern
 *  match on title + body + tags — no LLM call. Used to pre-select the
 *  Prep tab inside the AI workspace. */
const REVIEW_PATTERNS = [
  /\breview\b/i, /\brevision\b/i, /\btest\b/i, /\bexam\b/i,
  /\bassessment\b/i, /\bquiz\b/i, /\bmock\b/i,
  /\bmid[- ]?term\b/i, /\bunit\s*\d+\b/i,
  /पुनरावृत्ति|परीक्षा|प्रश्नोत्तरी/,
];

export function isReviewLike(
  a: Pick<Assignment, "title" | "title_en" | "body" | "notes_en" | "tags">,
): boolean {
  if (a.tags && (a.tags.includes("revision") || a.tags.includes("re-do"))) {
    return true;
  }
  const blob = [a.title, a.title_en, a.body, a.notes_en]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return REVIEW_PATTERNS.some((re) => re.test(blob));
}

/** Tiny "🤖 AI" pill on every assignment row. Click → opens the
 *  PracticePanel with three tabs (Prep / Help / Check). Defaults to
 *  Prep for review-like rows, Help otherwise — but the parent can
 *  switch tabs inside the panel.
 */
export function ReviewPracticeButton({
  a,
  className,
}: {
  a: Assignment;
  className?: string;
}) {
  const [open, setOpen] = useState<PracticeKind | null>(null);
  const onlyForAssignments = a.kind === "assignment" || a.kind === undefined;
  if (!onlyForAssignments) return null;
  const initialKind: PracticeKind = isReviewLike(a) ? "review_prep" : "assignment_help";

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(initialKind);
        }}
        className={
          (className ?? "") +
          " shrink-0 inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full" +
          " bg-gradient-to-r from-purple-100 via-amber-100 to-emerald-100" +
          " text-gray-800 border border-gray-300 hover:from-purple-200 hover:via-amber-200 hover:to-emerald-200"
        }
        title="Open AI workspace · prep / help / check"
        aria-label="Open AI workspace"
      >
        🤖 AI
      </button>
      {open && (
        <PracticePanel
          childId={a.child_id}
          subject={a.subject || "Subject"}
          linkedAssignment={a}
          topic={a.syllabus_context || null}
          kind={open}
          onClose={() => setOpen(null)}
        />
      )}
    </>
  );
}
