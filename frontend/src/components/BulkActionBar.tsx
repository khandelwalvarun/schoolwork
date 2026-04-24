import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, AssignmentPatch, ParentStatus } from "../api";

/** Floating action bar. Appears at bottom-center when `selectedIds.length > 0`.
 * All actions PATCH every selected id in parallel and invalidate queries
 * once at the end. Pass a `scope` label (e.g. "Overdue · Tejas") for the
 * header readout. */
export default function BulkActionBar({
  selectedIds,
  onClear,
  scope,
}: {
  selectedIds: number[];
  onClear: () => void;
  scope?: string;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [priorityOpen, setPriorityOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const snoozeRef = useRef<HTMLButtonElement | null>(null);
  const priorityRef = useRef<HTMLButtonElement | null>(null);
  const statusRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (snoozeRef.current && !snoozeRef.current.parentElement?.contains(t)) setSnoozeOpen(false);
      if (priorityRef.current && !priorityRef.current.parentElement?.contains(t)) setPriorityOpen(false);
      if (statusRef.current && !statusRef.current.parentElement?.contains(t)) setStatusOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  if (selectedIds.length === 0) return null;

  const apply = async (patch: AssignmentPatch) => {
    setBusy(true);
    try {
      await Promise.all(selectedIds.map((id) => api.patchAssignment(id, patch)));
      await qc.invalidateQueries();
    } finally {
      setBusy(false);
      setSnoozeOpen(false);
      setPriorityOpen(false);
      setStatusOpen(false);
    }
  };

  const daysFromNow = (n: number) => {
    const d = new Date(); d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
  };
  const nextWeekend = () => {
    const d = new Date(); const dow = d.getDay();
    const delta = (6 - dow + 7) % 7 || 7;
    return daysFromNow(delta);
  };

  const SNOOZE_PRESETS: { label: string; iso: string }[] = [
    { label: "Tomorrow",   iso: daysFromNow(1) },
    { label: "In 2 days",  iso: daysFromNow(2) },
    { label: "In 3 days",  iso: daysFromNow(3) },
    { label: "Weekend",    iso: nextWeekend() },
    { label: "In 1 week",  iso: daysFromNow(7) },
    { label: "In 2 weeks", iso: daysFromNow(14) },
  ];

  const STATUS_CHOICES: { label: string; value: ParentStatus | null }[] = [
    { label: "In progress",    value: "in_progress"  },
    { label: "Done at home",   value: "done_at_home" },
    { label: "Handed in",      value: "submitted"    },
    { label: "Needs help",     value: "needs_help"   },
    { label: "Blocked",        value: "blocked"      },
    { label: "Skipped",        value: "skipped"      },
    { label: "Clear status",   value: null           },
  ];

  const btn =
    "px-2.5 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50 " +
    "active:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-white border border-gray-300 rounded-xl shadow-2xl px-3 py-2 flex items-center gap-2"
      role="toolbar"
      aria-label={`Bulk actions for ${selectedIds.length} items`}
    >
      <div className="text-sm font-medium pr-2 border-r border-gray-200">
        <b>{selectedIds.length}</b> selected
        {scope && <span className="text-xs text-gray-500 ml-2">{scope}</span>}
      </div>

      <button
        className={btn + " bg-emerald-50 border-emerald-300 text-emerald-800 hover:bg-emerald-100"}
        onClick={() => apply({ parent_status: "done_at_home" })}
        disabled={busy}
        title="Mark all as done at home"
      >
        ✓ Done
      </button>

      <div className="relative">
        <button
          ref={snoozeRef}
          className={btn}
          onClick={() => setSnoozeOpen((v) => !v)}
          disabled={busy}
          aria-expanded={snoozeOpen}
        >
          💤 Snooze ▾
        </button>
        {snoozeOpen && (
          <div className="absolute bottom-full mb-2 right-0 bg-white border border-gray-300 rounded-lg shadow-xl py-1 min-w-[180px] text-sm">
            {SNOOZE_PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => apply({ snooze_until: p.iso })}
                className="flex items-center justify-between w-full text-left px-3 py-1.5 hover:bg-gray-50"
              >
                <span>{p.label}</span>
                <span className="text-xs text-gray-400 ml-4">{p.iso}</span>
              </button>
            ))}
            <div className="border-t border-gray-100 my-1" />
            <button
              onClick={() => apply({ snooze_until: null })}
              className="w-full text-left px-3 py-1.5 text-red-700 hover:bg-red-50"
            >
              Clear snooze
            </button>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          ref={priorityRef}
          className={btn}
          onClick={() => setPriorityOpen((v) => !v)}
          disabled={busy}
          aria-expanded={priorityOpen}
        >
          ★ Priority ▾
        </button>
        {priorityOpen && (
          <div className="absolute bottom-full mb-2 right-0 bg-white border border-gray-300 rounded-lg shadow-xl py-1 min-w-[120px] text-sm">
            {[0, 1, 2, 3].map((n) => (
              <button
                key={n}
                onClick={() => apply({ priority: n })}
                className="flex items-center gap-3 w-full text-left px-3 py-1.5 hover:bg-gray-50"
              >
                <span className="text-amber-500">{n === 0 ? "∅" : "★".repeat(n)}</span>
                <span>{n === 0 ? "None" : `Priority ${n}`}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="relative">
        <button
          ref={statusRef}
          className={btn}
          onClick={() => setStatusOpen((v) => !v)}
          disabled={busy}
          aria-expanded={statusOpen}
        >
          Status ▾
        </button>
        {statusOpen && (
          <div className="absolute bottom-full mb-2 right-0 bg-white border border-gray-300 rounded-lg shadow-xl py-1 min-w-[180px] text-sm">
            {STATUS_CHOICES.map((s) => (
              <button
                key={s.label}
                onClick={() => apply({ parent_status: s.value })}
                className={
                  "w-full text-left px-3 py-1.5 hover:bg-gray-50 " +
                  (s.value === null ? "text-red-700" : "")
                }
              >
                {s.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="pl-2 border-l border-gray-200">
        <button
          onClick={onClear}
          className="text-sm text-gray-500 hover:text-gray-900 px-2"
          aria-label="Deselect all"
          title="Deselect all"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
