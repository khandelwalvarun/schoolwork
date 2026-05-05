/**
 * CommandPalette — global ⌘K / Ctrl-K palette.
 *
 * Built on `cmdk` (the Vercel/Linear/Raycast-style palette primitive).
 * Gains over the previous home-rolled version:
 *   - Proper fuzzy match (not just substring)
 *   - Grouping by category renders headers automatically
 *   - Each item renders its keyboard shortcut alongside (Superhuman pattern)
 *   - Built-in a11y: aria-activedescendant, role="combobox" + listbox, etc.
 *
 * Items group:
 *   - Pages       (Today, Messages, Files, Notes, Summaries, Notifs, Settings)
 *   - Per kid     (Overview / Board / Assignments / Grades / Comments / Syllabus)
 *   - Actions     (Sync now, Send digest, Recheck syllabus, View sync log)
 *   - Assignments (jump to one — opens audit drawer via URL hash)
 *
 * Recents are not yet persisted — adding that is a small follow-up
 * (localStorage of last 5 selected ids).
 */
import { Command } from "cmdk";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, Assignment, Child } from "../api";

type Item = {
  id: string;
  group: "Pages" | "Kids" | "Actions" | "Assignments";
  label: string;
  hint?: string;
  shortcut?: string;
  keywords?: string[];
  action: () => void;
};

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
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

  const { data: children } = useQuery<Child[]>({
    queryKey: ["children"],
    queryFn: api.children,
    enabled: open,
  });
  const { data: today } = useQuery({
    queryKey: ["today"],
    queryFn: api.today,
    enabled: open,
  });

  const items = useMemo<Item[]>(() => {
    const xs: Item[] = [
      { id: "p:today",    group: "Pages", label: "Today",         shortcut: "g t", action: () => navigate("/") },
      { id: "p:messages", group: "Pages", label: "Messages",      shortcut: "g m", action: () => navigate("/messages") },
      { id: "p:files",    group: "Pages", label: "Files",         action: () => navigate("/attachments") },
      { id: "p:resources", group: "Pages", label: "Resources",    action: () => navigate("/resources") },
      { id: "p:spelling", group: "Pages", label: "Spelling",      action: () => navigate("/spellbee") },
      { id: "p:notes",    group: "Pages", label: "Notes",         action: () => navigate("/notes") },
      { id: "p:summaries", group: "Pages", label: "Summaries",    action: () => navigate("/summaries") },
      { id: "p:notifs",   group: "Pages", label: "Notifications", action: () => navigate("/notifications") },
      { id: "p:settings", group: "Pages", label: "Settings",      action: () => navigate("/settings") },
      { id: "p:vc",       group: "Pages", label: "Veracross settings", action: () => navigate("/settings/veracross") },
    ];
    for (const c of children || []) {
      const tag = c.class_section ? `· ${c.class_section}` : "";
      xs.push({ id: `k:${c.id}:o`,  group: "Kids", label: `${c.display_name} · Overview`,    hint: tag, action: () => navigate(`/child/${c.id}`) });
      xs.push({ id: `k:${c.id}:b`,  group: "Kids", label: `${c.display_name} · Board`,       hint: tag, action: () => navigate(`/child/${c.id}/board`) });
      xs.push({ id: `k:${c.id}:a`,  group: "Kids", label: `${c.display_name} · Assignments`, hint: tag, action: () => navigate(`/child/${c.id}/assignments`) });
      xs.push({ id: `k:${c.id}:g`,  group: "Kids", label: `${c.display_name} · Grades`,      hint: tag, action: () => navigate(`/child/${c.id}/grades`) });
      xs.push({ id: `k:${c.id}:c`,  group: "Kids", label: `${c.display_name} · Comments`,    hint: tag, action: () => navigate(`/child/${c.id}/comments`) });
      xs.push({ id: `k:${c.id}:s`,  group: "Kids", label: `${c.display_name} · Syllabus`,    hint: tag, action: () => navigate(`/child/${c.id}/syllabus`) });
    }
    xs.push({ id: "a:sync",     group: "Actions", label: "Sync now",         shortcut: "s",   action: () => { api.syncNow(); } });
    xs.push({ id: "a:digest",   group: "Actions", label: "Send digest now", action: () => { api.digestRun(); } });
    xs.push({ id: "a:syllabus", group: "Actions", label: "Recheck syllabus", action: () => { fetch("/api/syllabus/check-now", { method: "POST" }); } });
    xs.push({ id: "a:synclog",  group: "Actions", label: "View sync log",    action: () => { document.dispatchEvent(new CustomEvent("pc:synclog:open")); } });
    xs.push({ id: "a:matchgrades", group: "Actions", label: "Match grades to assignments", action: () => { fetch("/api/match-grades", { method: "POST" }); } });

    if (today) {
      const seen: Assignment[] = [];
      for (const k of today.children) {
        for (const a of [...k.overdue, ...k.due_today, ...k.upcoming]) seen.push(a);
      }
      for (const a of seen.slice(0, 80)) {
        xs.push({
          id: `as:${a.id}`,
          group: "Assignments",
          label: `${a.subject ?? ""} · ${a.title ?? "(untitled)"}`,
          hint: a.due_or_date ?? undefined,
          keywords: [a.title_en ?? "", a.subject ?? ""].filter(Boolean),
          action: () => navigate(`/child/${a.child_id}/assignments#a=${a.id}`),
        });
      }
    }
    return xs;
  }, [children, today, navigate]);

  const grouped = useMemo(() => {
    const out: Record<Item["group"], Item[]> = {
      Pages: [], Kids: [], Actions: [], Assignments: [],
    };
    for (const x of items) out[x.group].push(x);
    return out;
  }, [items]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-modal flex items-start justify-center pt-[12vh]"
      style={{ background: "rgba(0,0,0,0.35)" }}
      onClick={() => setOpen(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[600px] max-w-[92vw] bg-white rounded-xl shadow-2xl border border-[color:var(--line)] overflow-hidden"
      >
        <Command label="Command palette" loop>
          <Command.Input
            autoFocus
            placeholder="Search assignments, kids, pages, actions… (⌘K)"
            className="w-full px-4 py-3 text-base border-b border-[color:var(--line-soft)] outline-none"
          />
          <Command.List className="max-h-[55vh] overflow-y-auto">
            <Command.Empty className="px-4 py-6 text-center text-sm text-gray-500">
              No matches.
            </Command.Empty>
            {(Object.keys(grouped) as Item["group"][]).map((g) =>
              grouped[g].length === 0 ? null : (
                <Command.Group key={g} heading={g} className="px-2 pt-2 pb-1 text-[10px] uppercase tracking-wider text-gray-500">
                  {grouped[g].map((it) => (
                    <Command.Item
                      key={it.id}
                      value={`${it.label} ${it.hint ?? ""} ${(it.keywords ?? []).join(" ")}`}
                      onSelect={() => { it.action(); setOpen(false); }}
                      className={
                        "flex items-center justify-between gap-3 px-3 py-2 text-sm cursor-pointer rounded " +
                        "data-[selected=true]:bg-[color:var(--accent-bg)] data-[selected=true]:text-gray-900"
                      }
                    >
                      <span className="truncate">{it.label}</span>
                      <span className="flex items-center gap-2 flex-shrink-0">
                        {it.hint && <span className="text-xs text-gray-400">{it.hint}</span>}
                        {it.shortcut && <span className="kbd">{it.shortcut}</span>}
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              ),
            )}
          </Command.List>
          <div className="px-4 py-2 border-t border-[color:var(--line-soft)] text-xs text-gray-500 flex justify-between">
            <span><span className="kbd">↑</span> <span className="kbd">↓</span> navigate · <span className="kbd">⏎</span> open</span>
            <span><span className="kbd">esc</span> close</span>
          </div>
        </Command>
      </div>
    </div>
  );
}
