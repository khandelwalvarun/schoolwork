import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Assignment, api } from "../api";
import { formatDate } from "../util/dates";
import { useOptimisticPatch } from "./useOptimisticPatch";

/** Tray of items the parent flagged as "worth a chat" at the next PTM.
 *  Shows on each kid's detail page below the buckets; the same data
 *  feeds the PTM-brief synthesis. Empty state is hidden — no surface
 *  noise when nothing is flagged.
 *
 *  Each row exposes:
 *    - kind chip (assignment / grade / comment / message)
 *    - subject + title (clicks open the full audit drawer at that item)
 *    - the parent's note inline (if any)
 *    - inline "edit note" + "clear" affordances
 */
export function WorthAChatTray({
  childId,
  onOpenAudit,
}: {
  childId: number;
  onOpenAudit?: (a: Assignment) => void;
}) {
  const qc = useQueryClient();
  const optimisticPatch = useOptimisticPatch();
  const { data, isLoading } = useQuery({
    queryKey: ["worth-a-chat", childId],
    queryFn: () => api.worthAChat(childId),
    refetchInterval: 30_000,
  });

  if (isLoading) return null;
  if (!data || data.length === 0) return null;

  const kindChip: Record<string, string> = {
    assignment: "chip-blue",
    grade: "chip-green",
    comment: "chip-amber",
    school_message: "chip-gray",
    message: "chip-gray",
  };

  const editNote = async (a: Assignment) => {
    const next = window.prompt(
      "Reason for chatting about this with the teacher (blank to remove):",
      a.discuss_with_teacher_note || "",
    );
    if (next === null) return; // Cancel
    await optimisticPatch(
      a.id,
      { discuss_with_teacher_note: next.trim() || null },
      { label: "Reason updated" },
    );
    qc.invalidateQueries({ queryKey: ["worth-a-chat"] });
  };

  const clearFlag = async (a: Assignment) => {
    await optimisticPatch(
      a.id,
      { discuss_with_teacher: false },
      { label: "Cleared from PTM list" },
    );
    qc.invalidateQueries({ queryKey: ["worth-a-chat"] });
  };

  return (
    <section className="surface mb-6 p-4 border-l-4 border-violet-400">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="h-section text-violet-800">
          💬 Worth a chat at PTM · {data.length}
        </h3>
        <span className="text-xs text-gray-500">
          Flagged items will surface in the PTM brief.
        </span>
      </div>
      <ul className="space-y-2">
        {data.map((a) => (
          <li
            key={a.id}
            className="flex items-start gap-2 px-3 py-2 rounded border border-violet-100 bg-violet-50/40 hover:bg-violet-50 cursor-pointer"
            onClick={() => onOpenAudit && onOpenAudit(a)}
          >
            <span className={(kindChip[a.kind || "assignment"] || "chip-gray") + " text-[10px] mt-0.5"}>
              {a.kind || "assignment"}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-gray-600">{a.subject}</span>
                <span className="text-gray-400">·</span>
                <span className="truncate font-medium" title={a.title || ""}>
                  {a.title_en || a.title || "(untitled)"}
                </span>
                {a.due_or_date && (
                  <span className="text-xs text-gray-500 ml-auto whitespace-nowrap">
                    {formatDate(a.due_or_date)}
                  </span>
                )}
              </div>
              {a.discuss_with_teacher_note ? (
                <div className="text-xs text-violet-900 mt-0.5">
                  ↳ {a.discuss_with_teacher_note}
                </div>
              ) : (
                <div className="text-xs text-gray-400 italic mt-0.5">
                  no reason yet — click ✎ to add one
                </div>
              )}
            </div>
            <div
              className="flex items-center gap-1 shrink-0"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => editNote(a)}
                title="Edit reason"
                aria-label="Edit reason"
                className="text-violet-700 hover:bg-violet-100 rounded px-1.5 py-0.5 text-sm"
              >
                ✎
              </button>
              <button
                onClick={() => clearFlag(a)}
                title="Remove from PTM list"
                aria-label="Remove from PTM list"
                className="text-gray-500 hover:text-red-700 hover:bg-red-50 rounded px-1.5 py-0.5 text-sm"
              >
                ✕
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
