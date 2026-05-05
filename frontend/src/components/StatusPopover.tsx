import { useEffect, useRef, useState } from "react";
import { Assignment, ParentStatus } from "../api";
import { useOptimisticPatch } from "./useOptimisticPatch";
import { useFloatingPosition } from "./useFloatingPosition";
import { daysFromTodayIST, todayISOInIST } from "../util/ist";
import { EFFECTIVE_STATUS_LABEL, PARENT_STATUS_LABEL } from "../util/strings";

// Visual metadata only — text labels read from `PARENT_STATUS_LABEL`
// in util/strings.ts so the parent-facing vocabulary lives in one
// place.
const PARENT_STATUS_DOT: Record<ParentStatus, string> = {
  in_progress:  "bg-amber-500",
  done_at_home: "bg-emerald-500",
  submitted:    "bg-blue-500",
  needs_help:   "bg-orange-500",
  blocked:      "bg-rose-500",
  skipped:      "bg-gray-400",
};

// Three primary statuses cover ~90 % of parent use. The other three
// (handed-in / blocked / skipped) hide behind "More options" so the
// popover's first impression is a single decision: in progress / done
// / needs help.
const PRIMARY_STATUSES: ParentStatus[] = ["in_progress", "done_at_home", "needs_help"];
const SECONDARY_STATUSES: ParentStatus[] = ["submitted", "blocked", "skipped"];

const EFFECTIVE_CHIP: Record<string, string> = {
  graded: "chip-green",
  submitted: "chip-blue",
  done_at_home: "chip-green",
  in_progress: "chip-amber",
  needs_help: "chip-amber",
  blocked: "chip-red",
  skipped: "chip-amber",
  overdue: "chip-red",
  pending: "chip-amber",
};

// Visual mapping only; labels live in util/strings.ts.
export function EffectiveStatusChip({ a }: { a: Assignment }) {
  const eff = a.effective_status || "pending";
  const cls = EFFECTIVE_CHIP[eff] || "chip-amber";
  const label = EFFECTIVE_STATUS_LABEL[eff] || eff;
  return <span className={cls}>{label}</span>;
}

// IST-anchored — don't let the device's timezone drift the date.
const daysFromNow = daysFromTodayIST;

const FIXED_TAGS = [
  "needs-printing",
  "needs-parent-help",
  "needs-teacher-help",
  "missing-materials",
  "tomorrow",
  "weekend",
  "revision",
  "re-do",
];

export default function StatusPopover({
  a,
  onClose,
  onSaved,
  anchorRect,
}: {
  a: Assignment;
  onClose: () => void;
  onSaved?: () => void;
  anchorRect?: DOMRect;
}) {
  const optimisticPatch = useOptimisticPatch();
  const ref = useRef<HTMLDivElement | null>(null);
  const [parentStatus, setParentStatus] = useState<ParentStatus | null>(a.parent_status);
  const [priority, setPriority] = useState<number>(a.priority || 0);
  const [snooze, setSnooze] = useState<string | null>(a.snooze_until);
  const [tags, setTags] = useState<string[]>(a.tags || []);
  const [note, setNote] = useState<string>(a.status_notes || "");
  const [worthAChat, setWorthAChat] = useState<boolean>(!!a.discuss_with_teacher_at);
  const [worthAChatNote, setWorthAChatNote] = useState<string>(
    a.discuss_with_teacher_note || ""
  );
  const [saving, setSaving] = useState(false);
  // "More options" — opens secondary statuses, priority, tags, notes.
  // Auto-open if the row already has any of those set, so editing
  // existing data doesn't hide it.
  const [showMore, setShowMore] = useState(
    !!a.priority ||
      !!a.snooze_until ||
      (a.tags?.length ?? 0) > 0 ||
      !!a.status_notes ||
      (a.parent_status != null && SECONDARY_STATUSES.includes(a.parent_status as ParentStatus)),
  );

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [onClose]);

  const toggleTag = (t: string) => {
    setTags((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  };

  const save = async () => {
    setSaving(true);
    try {
      await optimisticPatch(a.id, {
        parent_status: parentStatus ?? null,
        priority,
        snooze_until: snooze ?? null,
        status_notes: note || null,
        tags,
        // Only emit the flag fields when they actually changed — avoids
        // re-stamping discuss_with_teacher_at every save.
        ...(worthAChat !== !!a.discuss_with_teacher_at
          ? { discuss_with_teacher: worthAChat }
          : {}),
        ...(worthAChat
          ? { discuss_with_teacher_note: worthAChatNote || null }
          : {}),
      }, { label: "Status updated" });
      if (onSaved) onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const floatingPos = useFloatingPosition(anchorRect ?? null, ref);
  const fallbackPos = anchorRect
    ? { top: anchorRect.bottom + window.scrollY + 4, left: anchorRect.left + window.scrollX }
    : undefined;

  return (
    <div
      ref={ref}
      style={{
        position: "absolute",
        // Popover sits above drawers but below modals — it's a
        // contextual editor, not a focused dialog.
        zIndex: "var(--z-modal)" as unknown as number,
        top: floatingPos?.top ?? fallbackPos?.top,
        left: floatingPos?.left ?? fallbackPos?.left,
        // Hide first paint until clamping resolves so we never flash off-screen.
        visibility: anchorRect && !floatingPos ? "hidden" : "visible",
      }}
      className="bg-white border border-gray-300 rounded-lg shadow-xl p-4 w-[360px] text-sm"
    >
      <div className="flex items-baseline justify-between mb-3">
        <b>Update status</b>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
      </div>

      {/* Primary: a single decision — what's the kid's status?
          Three big buttons. "Not tracked" stays as a clear option to
          undo a previous mark. */}
      <div className="mb-3">
        <div className="grid grid-cols-2 gap-1">
          <button
            onClick={() => setParentStatus(null)}
            className={
              "px-2 py-1.5 rounded border text-left " +
              (parentStatus === null
                ? "border-blue-500 bg-blue-50 text-blue-800"
                : "border-gray-200 hover:bg-gray-50")
            }
          >
            <span className="inline-block w-2 h-2 rounded-full mr-2 bg-gray-300" /> Not tracked
          </button>
          {PRIMARY_STATUSES.map((k) => (
            <button
              key={k}
              onClick={() => setParentStatus(k)}
              className={
                "px-2 py-1.5 rounded border text-left " +
                (parentStatus === k
                  ? "border-blue-500 bg-blue-50 text-blue-800"
                  : "border-gray-200 hover:bg-gray-50")
              }
            >
              <span className={`inline-block w-2 h-2 rounded-full mr-2 ${PARENT_STATUS_DOT[k]}`} />
              {PARENT_STATUS_LABEL[k]}
            </button>
          ))}
        </div>
      </div>

      {/* Snooze — every parent uses this. Kept primary. */}
      <div className="mb-3">
        <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Snooze until</div>
        <div className="flex gap-1 flex-wrap items-center">
          <button onClick={() => setSnooze(daysFromNow(1))}
            className={"px-2 py-0.5 rounded border text-xs " + (snooze === daysFromNow(1) ? "border-blue-500 bg-blue-50" : "border-gray-200")}>
            Tomorrow
          </button>
          <button onClick={() => {
            const [yy, mm, dd] = todayISOInIST().split("-").map(Number);
            const anchor = new Date(Date.UTC(yy, mm - 1, dd));
            const dow = anchor.getUTCDay();
            const delta = (6 - dow + 7) % 7 || 7;
            setSnooze(daysFromNow(delta));
          }}
            className={"px-2 py-0.5 rounded border text-xs border-gray-200 hover:bg-gray-50"}>
            Weekend
          </button>
          <input type="date"
            value={snooze || ""}
            onChange={(e) => setSnooze(e.target.value || null)}
            className="px-1 py-0.5 rounded border border-gray-200 text-xs" />
          {snooze && (
            <button onClick={() => setSnooze(null)} className="text-xs text-red-700">clear</button>
          )}
        </div>
      </div>

      {/* Worth a chat — a one-line, parent-friendly nudge. Kept primary. */}
      <div className="mb-3 p-2 rounded border border-violet-200 bg-violet-50/40">
        <label className="flex items-center gap-2 text-xs font-semibold text-violet-900 cursor-pointer">
          <input
            type="checkbox"
            checked={worthAChat}
            onChange={(e) => setWorthAChat(e.target.checked)}
            className="h-3.5 w-3.5 accent-violet-700"
          />
          <span>💬 Worth a chat at the next PTM</span>
        </label>
        {worthAChat && (
          <input
            type="text"
            placeholder="Optional reason"
            value={worthAChatNote}
            onChange={(e) => setWorthAChatNote(e.target.value)}
            className="w-full border border-violet-200 rounded px-2 py-1 text-xs mt-1"
          />
        )}
      </div>

      {/* More options — opens secondary statuses, priority, tags, notes.
          Auto-expanded if any of those fields already have data so
          editing existing entries doesn't hide them. */}
      <button
        type="button"
        onClick={() => setShowMore((x) => !x)}
        className="text-xs text-gray-500 hover:text-gray-800 mb-2 flex items-center gap-1"
      >
        <span className={"inline-block transition-transform " + (showMore ? "rotate-90" : "")}>▶</span>
        <span>{showMore ? "Hide" : "More"} options</span>
      </button>

      {showMore && (
        <>
          <div className="mb-3">
            <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Other statuses</div>
            <div className="grid grid-cols-3 gap-1">
              {SECONDARY_STATUSES.map((k) => (
                <button
                  key={k}
                  onClick={() => setParentStatus(k)}
                  className={
                    "px-2 py-1 rounded border text-left text-xs " +
                    (parentStatus === k
                      ? "border-blue-500 bg-blue-50 text-blue-800"
                      : "border-gray-200 hover:bg-gray-50")
                  }
                >
                  <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${PARENT_STATUS_DOT[k]}`} />
                  {PARENT_STATUS_LABEL[k]}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-3">
            <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Priority</div>
            <div className="flex gap-1">
              {[0, 1, 2, 3].map((n) => (
                <button
                  key={n}
                  onClick={() => setPriority(n)}
                  className={
                    "text-lg " + (priority >= n && n > 0 ? "text-amber-500" : "text-gray-300")
                  }
                  title={`Priority ${n}`}
                >
                  {n === 0 ? "∅" : "★"}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-3">
            <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Tags</div>
            <div className="flex flex-wrap gap-1">
              {FIXED_TAGS.map((t) => (
                <button
                  key={t}
                  onClick={() => toggleTag(t)}
                  className={
                    "px-2 py-0.5 rounded-full border text-xs " +
                    (tags.includes(t)
                      ? "border-blue-500 bg-blue-50 text-blue-800"
                      : "border-gray-200 text-gray-600 hover:bg-gray-50")
                  }
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-3">
            <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Note</div>
            <textarea
              rows={2}
              className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
              placeholder="e.g. emailed teacher today"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </>
      )}

      <div className="flex gap-2 justify-end">
        <button onClick={onClose} className="px-3 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50">Cancel</button>
        <button
          disabled={saving}
          onClick={save}
          className="px-3 py-1 rounded bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
