import { useState } from "react";
import { Assignment, PracticeKind } from "../api";
import { PracticePanel } from "./PracticePanel";

/** Phase 26 — read Veracross's own `type` (mapped server-side to
 *  work_category) instead of regex-guessing from the title. The
 *  school is the authoritative source. Manual `revision` / `re-do`
 *  tags still override (parent override). */
export function isReviewLike(
  a: Pick<Assignment, "work_category" | "tags">,
): boolean {
  if (a.tags && (a.tags.includes("revision") || a.tags.includes("re-do"))) {
    return true;
  }
  return a.work_category === "review";
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
  // Classwork is done in class — no parent prep needed; skip the button.
  if (a.work_category === "classwork") return null;
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
