import { useEffect, useRef, useState } from "react";
import { Assignment, ParentStatus } from "../api";
import { useOptimisticPatch } from "./useOptimisticPatch";
import { useFloatingPosition } from "./useFloatingPosition";
import { daysFromTodayIST, todayISOInIST } from "../util/ist";

const PARENT_STATUS_LABELS: Record<ParentStatus, { label: string; dot: string; chip: string }> = {
  in_progress:  { label: "In progress",     dot: "bg-amber-500",   chip: "chip-amber" },
  done_at_home: { label: "Done at home",    dot: "bg-emerald-500", chip: "chip-green" },
  submitted:    { label: "Handed in",       dot: "bg-blue-500",    chip: "chip-blue"  },
  needs_help:   { label: "Needs help",      dot: "bg-orange-500",  chip: "chip-amber" },
  blocked:      { label: "Blocked",         dot: "bg-rose-500",    chip: "chip-red"   },
  skipped:      { label: "Skipped",         dot: "bg-gray-400",    chip: "chip-amber" },
};

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

const EFFECTIVE_LABEL: Record<string, string> = {
  graded: "graded",
  submitted: "submitted",
  done_at_home: "done",
  in_progress: "in progress",
  needs_help: "needs help",
  blocked: "blocked",
  skipped: "skipped",
  overdue: "overdue",
  pending: "pending",
};

export function EffectiveStatusChip({ a }: { a: Assignment }) {
  const eff = a.effective_status || "pending";
  const cls = EFFECTIVE_CHIP[eff] || "chip-amber";
  const label = EFFECTIVE_LABEL[eff] || eff;
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
        zIndex: 1000,
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

      <div className="mb-3">
        <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Parent status</div>
        <div className="grid grid-cols-2 gap-1">
          <button
            onClick={() => setParentStatus(null)}
            className={
              "px-2 py-1 rounded border text-left " +
              (parentStatus === null
                ? "border-blue-500 bg-blue-50 text-blue-800"
                : "border-gray-200 hover:bg-gray-50")
            }
          >
            <span className="inline-block w-2 h-2 rounded-full mr-2 bg-gray-300" /> Not tracked
          </button>
          {Object.entries(PARENT_STATUS_LABELS).map(([k, v]) => (
            <button
              key={k}
              onClick={() => setParentStatus(k as ParentStatus)}
              className={
                "px-2 py-1 rounded border text-left " +
                (parentStatus === k
                  ? "border-blue-500 bg-blue-50 text-blue-800"
                  : "border-gray-200 hover:bg-gray-50")
              }
            >
              <span className={`inline-block w-2 h-2 rounded-full mr-2 ${v.dot}`} />
              {v.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-4 mb-3">
        <div>
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
        <div className="flex-1">
          <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Snooze until</div>
          <div className="flex gap-1 flex-wrap">
            <button onClick={() => setSnooze(daysFromNow(1))}
              className={"px-2 py-0.5 rounded border text-xs " + (snooze === daysFromNow(1) ? "border-blue-500 bg-blue-50" : "border-gray-200")}>
              Tomorrow
            </button>
            <button onClick={() => {
              // Next Saturday in IST — see util/ist.ts
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

      <div className="mb-3 p-2 rounded border border-violet-200 bg-violet-50/40">
        <label className="flex items-center gap-2 text-xs font-semibold text-violet-900 mb-1 cursor-pointer">
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
            placeholder="Optional reason — e.g. ask why score dropped"
            value={worthAChatNote}
            onChange={(e) => setWorthAChatNote(e.target.value)}
            className="w-full border border-violet-200 rounded px-2 py-1 text-xs mt-1"
          />
        )}
      </div>

      <div className="mb-3">
        <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Note</div>
        <textarea
          rows={2}
          className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
          placeholder="e.g. emailed teacher 2026-04-24"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>

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
