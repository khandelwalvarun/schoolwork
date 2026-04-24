import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, Assignment, ParentStatus } from "../api";
import StatusPopover from "./StatusPopover";

/** Row-level one-click actions for an assignment.
 *   ✓     — toggle done-at-home
 *   💤    — dropdown: 1d / 3d / weekend / 1w / 2w / pick date / clear
 *   ⋯     — full StatusPopover (priority, tags, notes, other states)
 */
export default function QuickActions({ a }: { a: Assignment }) {
  const qc = useQueryClient();
  const moreRef = useRef<HTMLButtonElement | null>(null);
  const snoozeRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [popover, setPopover] = useState<DOMRect | null>(null);
  const [snoozeMenu, setSnoozeMenu] = useState<DOMRect | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!snoozeMenu) return;
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)
          && snoozeRef.current && !snoozeRef.current.contains(e.target as Node)) {
        setSnoozeMenu(null);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [snoozeMenu]);

  const patch = async (label: string, payload: Parameters<typeof api.patchAssignment>[1]) => {
    setBusy(label);
    try {
      await api.patchAssignment(a.id, payload);
      await qc.invalidateQueries();
    } finally {
      setBusy(null);
    }
  };

  const daysFromNow = (n: number): string => {
    const d = new Date(); d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
  };
  const nextWeekend = (): string => {
    const d = new Date(); const dow = d.getDay();  // 0 Sun 6 Sat
    const delta = (6 - dow + 7) % 7 || 7;
    return daysFromNow(delta);
  };

  const isDone = a.parent_status === "done_at_home" || a.parent_status === "submitted";
  const todayIso = new Date().toISOString().slice(0, 10);
  const isSnoozed = !!a.snooze_until && a.snooze_until > todayIso;

  const box =
    "w-7 h-7 inline-flex items-center justify-center rounded border text-sm transition-colors " +
    "hover:bg-gray-50 active:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed";

  const toggleDone = () => {
    const next: ParentStatus | null = isDone && a.parent_status === "done_at_home" ? null : "done_at_home";
    patch("done", { parent_status: next });
  };

  const snooze = (dateIso: string | null) => {
    setSnoozeMenu(null);
    patch("snooze", { snooze_until: dateIso });
  };

  const openSnoozeMenu = () => {
    const r = (snoozeRef.current as HTMLButtonElement).getBoundingClientRect();
    setSnoozeMenu(r);
  };

  const SNOOZE_PRESETS: { label: string; get: () => string }[] = [
    { label: "Tomorrow",  get: () => daysFromNow(1) },
    { label: "In 2 days", get: () => daysFromNow(2) },
    { label: "In 3 days", get: () => daysFromNow(3) },
    { label: "Weekend",   get: nextWeekend },
    { label: "In 1 week", get: () => daysFromNow(7) },
    { label: "In 2 weeks", get: () => daysFromNow(14) },
  ];

  return (
    <div className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <button
        className={box + (isDone ? " bg-emerald-50 border-emerald-400 text-emerald-800" : " border-gray-300 text-gray-500")}
        onClick={toggleDone}
        disabled={busy !== null}
        title={isDone ? "Mark not done" : "Mark done at home"}
        aria-label={isDone ? "Mark not done" : "Mark done at home"}
      >
        {isDone ? "✓" : "☐"}
      </button>
      <button
        ref={snoozeRef}
        className={box + (isSnoozed ? " bg-amber-50 border-amber-400 text-amber-800" : " border-gray-300 text-gray-500")}
        onClick={openSnoozeMenu}
        disabled={busy !== null}
        title={isSnoozed ? `Snoozed until ${a.snooze_until}` : "Snooze for N days"}
        aria-label="Snooze"
      >
        💤
      </button>
      <button
        ref={moreRef}
        className={box + " border-gray-300 text-gray-500"}
        onClick={() => {
          const r = (moreRef.current as HTMLButtonElement).getBoundingClientRect();
          setPopover(r);
        }}
        title="More actions (priority, tags, notes, other statuses)"
        aria-label="More actions"
      >
        ⋯
      </button>

      {snoozeMenu && (
        <div
          ref={menuRef}
          style={{
            position: "absolute",
            zIndex: 1000,
            top: snoozeMenu.bottom + window.scrollY + 4,
            left: snoozeMenu.left + window.scrollX,
            minWidth: 180,
          }}
          className="bg-white border border-gray-300 rounded-lg shadow-xl py-1 text-sm"
        >
          {isSnoozed && (
            <button
              onClick={() => snooze(null)}
              className="block w-full text-left px-3 py-1.5 text-red-700 hover:bg-red-50"
            >
              Clear snooze
              <span className="text-xs text-red-400 ml-2">{a.snooze_until}</span>
            </button>
          )}
          {SNOOZE_PRESETS.map((p) => {
            const iso = p.get();
            const isCurrent = a.snooze_until === iso;
            return (
              <button
                key={p.label}
                onClick={() => snooze(iso)}
                className={
                  "flex items-center justify-between w-full text-left px-3 py-1.5 hover:bg-gray-50 " +
                  (isCurrent ? "bg-amber-50 text-amber-800" : "")
                }
              >
                <span>{p.label}</span>
                <span className="text-xs text-gray-400 ml-4">{iso}</span>
              </button>
            );
          })}
          <div className="border-t border-gray-100 my-1" />
          <div className="px-3 py-1.5 flex items-center gap-2">
            <label className="text-xs text-gray-500">Pick date</label>
            <input
              type="date"
              min={todayIso}
              defaultValue={a.snooze_until || ""}
              onChange={(e) => { if (e.target.value) snooze(e.target.value); }}
              className="text-xs border border-gray-300 rounded px-1 py-0.5 flex-1"
            />
          </div>
        </div>
      )}

      {popover && (
        <StatusPopover a={a} anchorRect={popover} onClose={() => setPopover(null)} />
      )}
    </div>
  );
}
