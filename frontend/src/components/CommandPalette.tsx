import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, Assignment, Child } from "../api";

type Command = {
  id: string;
  label: string;
  hint?: string;
  shortcut?: string;
  action: () => void;
};

/** ⌘K / Ctrl-K anywhere opens a fuzzy command + jump palette.
 *
 *   - Pages:        Today, Messages, Files, Notes, Summaries,
 *                   Notifications, Settings, Board/Assignments/Grades
 *                   per child.
 *   - Actions:      Sync now, Send digest, Check syllabus now.
 *   - Assignments:  jump directly to an assignment (opens audit drawer).
 */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();

  // Global ⌘K / Ctrl-K hotkey
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open) {
      setQ("");
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  const { data: children } = useQuery({
    queryKey: ["children"],
    queryFn: api.children,
    enabled: open,
  });
  const { data: today } = useQuery({
    queryKey: ["today"],
    queryFn: api.today,
    enabled: open,
  });

  const commands = useMemo<Command[]>(() => {
    const cmds: Command[] = [
      { id: "nav:today",        label: "Go to: Today",         shortcut: "g t", action: () => navigate("/") },
      { id: "nav:messages",     label: "Go to: Messages",      action: () => navigate("/messages") },
      { id: "nav:files",        label: "Go to: Files",         action: () => navigate("/attachments") },
      { id: "nav:notes",        label: "Go to: Notes",         action: () => navigate("/notes") },
      { id: "nav:summaries",    label: "Go to: Summaries",     action: () => navigate("/summaries") },
      { id: "nav:notifs",       label: "Go to: Notifications", action: () => navigate("/notifications") },
      { id: "nav:settings",     label: "Go to: Settings",      action: () => navigate("/settings") },
    ];
    for (const c of (children as Child[] | undefined) || []) {
      cmds.push({ id: `kid:${c.id}:overview`, label: `Go to: ${c.display_name} · Overview`, hint: c.class_section ?? undefined, action: () => navigate(`/child/${c.id}`) });
      cmds.push({ id: `kid:${c.id}:board`,    label: `Go to: ${c.display_name} · Board`,    hint: c.class_section ?? undefined, action: () => navigate(`/child/${c.id}/board`) });
      cmds.push({ id: `kid:${c.id}:asgn`,     label: `Go to: ${c.display_name} · Assignments`, hint: c.class_section ?? undefined, action: () => navigate(`/child/${c.id}/assignments`) });
      cmds.push({ id: `kid:${c.id}:grades`,   label: `Go to: ${c.display_name} · Grades`,   hint: c.class_section ?? undefined, action: () => navigate(`/child/${c.id}/grades`) });
    }
    cmds.push({ id: "act:sync",      label: "Run: Sync now",            action: () => { api.syncNow(); } });
    cmds.push({ id: "act:digest",    label: "Run: Send digest now",     action: () => { api.digestRun(); } });
    cmds.push({ id: "act:syllabus",  label: "Run: Recheck syllabus",    action: () => { fetch("/api/syllabus/check-now", { method: "POST" }); } });
    // Assignments (top 60) — each a jump that opens audit drawer via URL hash
    const assignments: Assignment[] = [];
    if (today) {
      for (const k of today.children) {
        for (const a of [...k.overdue, ...k.due_today, ...k.upcoming]) {
          assignments.push(a);
        }
      }
    }
    for (const a of assignments.slice(0, 80)) {
      cmds.push({
        id: `asgn:${a.id}`,
        label: `${a.subject ?? ""}: ${a.title ?? ""}`.trim(),
        hint: a.due_or_date ?? undefined,
        action: () => {
          const kid = a.child_id;
          navigate(`/child/${kid}/assignments#a=${a.id}`);
        },
      });
    }
    return cmds;
  }, [children, today, navigate]);

  // Simple fuzzy-ish filter — substring match, case-insensitive, across label+hint.
  const filtered = useMemo(() => {
    if (!q.trim()) return commands.slice(0, 40);
    const tokens = q.toLowerCase().split(/\s+/).filter(Boolean);
    return commands
      .map((c) => {
        const hay = (c.label + " " + (c.hint || "")).toLowerCase();
        const matches = tokens.every((t) => hay.includes(t));
        return matches ? c : null;
      })
      .filter((x): x is Command => x !== null)
      .slice(0, 40);
  }, [q, commands]);

  useEffect(() => { setActiveIdx(0); }, [q]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const chosen = filtered[activeIdx];
      if (chosen) {
        chosen.action();
        setOpen(false);
      }
    }
  };

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh]"
      style={{ background: "rgba(0,0,0,0.35)" }}
      onClick={() => setOpen(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[560px] max-w-[92vw] bg-white rounded-xl shadow-2xl border border-[color:var(--line)] overflow-hidden"
      >
        <input
          ref={inputRef}
          className="w-full px-4 py-3 text-base border-b border-[color:var(--line-soft)] outline-none"
          placeholder="Search assignments, kids, pages, actions… (⌘K)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={handleKey}
        />
        <div className="max-h-[50vh] overflow-y-auto">
          {filtered.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-gray-500">No matches.</div>
          )}
          {filtered.map((c, i) => (
            <button
              key={c.id}
              onClick={() => { c.action(); setOpen(false); }}
              onMouseEnter={() => setActiveIdx(i)}
              className={
                "w-full flex items-center justify-between px-4 py-2 text-left text-sm " +
                (i === activeIdx ? "bg-[color:var(--accent-bg)] text-gray-900" : "hover:bg-gray-50")
              }
            >
              <span className="truncate">{c.label}</span>
              <span className="flex items-center gap-2 flex-shrink-0">
                {c.hint && <span className="text-xs text-gray-400">{c.hint}</span>}
                {c.shortcut && <span className="kbd">{c.shortcut}</span>}
              </span>
            </button>
          ))}
        </div>
        <div className="px-4 py-2 border-t border-[color:var(--line-soft)] text-xs text-gray-500 flex justify-between">
          <span><span className="kbd">↑</span> <span className="kbd">↓</span> navigate · <span className="kbd">⏎</span> open</span>
          <span><span className="kbd">esc</span> close</span>
        </div>
      </div>
    </div>
  );
}
