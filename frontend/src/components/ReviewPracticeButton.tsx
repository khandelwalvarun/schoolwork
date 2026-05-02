import { useState } from "react";
import { Assignment } from "../api";
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
  // Tag override — the parent (or a future classifier) can flag
  // anything as a review with the "revision" tag.
  if (a.tags && (a.tags.includes("revision") || a.tags.includes("re-do"))) {
    return true;
  }
  const blob = [a.title, a.title_en, a.body, a.notes_en]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return REVIEW_PATTERNS.some((re) => re.test(blob));
}

/** Tiny inline button shown on assignment rows that look like reviews.
 *  Clicking opens the PracticePanel slide-over for this kid + subject,
 *  pointed at this assignment row. */
export function ReviewPracticeButton({
  a,
  className,
}: {
  a: Assignment;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  if (!isReviewLike(a)) return null;
  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
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
      {open && (
        <PracticePanel
          childId={a.child_id}
          subject={a.subject || "Subject"}
          linkedAssignment={a}
          topic={a.syllabus_context || null}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
