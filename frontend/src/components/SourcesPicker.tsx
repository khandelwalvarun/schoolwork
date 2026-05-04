/**
 * SourcesPicker — modal for pinning grounding sources to a practice
 * session. Three tabs:
 *
 *   📚 Library    — parent-uploaded files (textbook PDFs, EPUBs, …)
 *   📁 Resources  — portal-harvested files under data/rawdata
 *   🎯 Syllabus   — topics from the kid's current cycle
 *
 * Multi-select within each tab — click an item to toggle pin. The
 * full pinned list (across all tabs) shows in a chip strip at the
 * top with × buttons. "Save" pushes the new list to the backend.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  LibraryFile,
  PinnedSource,
  PinnedSourceType,
  ResourceFile,
} from "../api";

type TabId = "library" | "resources" | "syllabus";

export function SourcesPicker({
  childId,
  classLevel,
  subject,
  initial,
  onSave,
  onClose,
}: {
  childId: number;
  classLevel: number | null;
  subject: string;
  initial: PinnedSource[];
  onSave: (sources: PinnedSource[]) => void;
  onClose: () => void;
}) {
  const [active, setActive] = useState<TabId>("library");
  const [pinned, setPinned] = useState<PinnedSource[]>(initial);
  const [search, setSearch] = useState("");

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const isPinned = (t: PinnedSourceType, ref: string | number) =>
    pinned.some((p) => p.type === t && String(p.ref) === String(ref));

  const togglePin = (s: PinnedSource) => {
    setPinned((prev) => {
      const exists = prev.some(
        (p) => p.type === s.type && String(p.ref) === String(s.ref),
      );
      if (exists) {
        return prev.filter(
          (p) => !(p.type === s.type && String(p.ref) === String(s.ref)),
        );
      }
      return [...prev, s];
    });
  };

  const removeAt = (idx: number) => {
    setPinned((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      onClick={onClose}
      style={{ background: "oklch(0% 0 0 / 0.45)" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-lg shadow-2xl flex flex-col"
        style={{ width: "min(720px, 100%)", height: "min(640px, 100vh)" }}
      >
        <header className="px-5 py-4 border-b border-gray-200 flex items-baseline justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold leading-tight">
              📚 Pin grounding sources
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Pinned items feed into every iteration's prompt as authoritative
              context. Library + resources contribute extracted text;
              syllabus topics narrow the LLM's focus.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-2xl text-gray-400 hover:text-gray-700 leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        {/* Pinned chips strip */}
        <div className="px-5 py-2 border-b border-gray-100 bg-gray-50 min-h-[48px]">
          {pinned.length === 0 ? (
            <span className="text-xs text-gray-400 italic">
              Nothing pinned yet — pick from the tabs below.
            </span>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {pinned.map((p, i) => (
                <span
                  key={`${p.type}-${p.ref}`}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border border-gray-300 bg-white"
                >
                  <span className="opacity-60">{typeIcon(p.type)}</span>
                  <span>{p.label}</span>
                  <button
                    onClick={() => removeAt(i)}
                    className="text-rose-600 hover:text-rose-800 ml-0.5"
                    aria-label={`Remove ${p.label}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Tabs */}
        <div role="tablist" className="px-5 pt-2 -mb-px flex items-center gap-1 border-b border-gray-200">
          {(["library", "resources", "syllabus"] as const).map((t) => {
            const isActive = active === t;
            return (
              <button
                key={t}
                role="tab"
                aria-selected={isActive}
                onClick={() => setActive(t)}
                className={
                  "px-3 py-2 text-sm font-medium border-b-2 transition-colors " +
                  (isActive
                    ? "border-purple-600 text-purple-700"
                    : "border-transparent text-gray-500 hover:text-gray-800")
                }
              >
                <span className="mr-1.5">{tabEmoji(t)}</span>
                {tabLabel(t)}
              </button>
            );
          })}
          <input
            type="text"
            placeholder="Filter…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="ml-auto text-sm px-2 py-1 border border-gray-300 rounded w-40"
          />
        </div>

        {/* Tab body */}
        <div className="flex-1 overflow-auto px-5 py-3">
          {active === "library" && (
            <LibraryTab
              childId={childId}
              search={search}
              isPinned={(id) => isPinned("library", id)}
              onToggle={(file) =>
                togglePin({
                  type: "library",
                  ref: file.id,
                  label: labelForLibrary(file),
                })
              }
            />
          )}
          {active === "resources" && (
            <ResourcesTab
              childId={childId}
              search={search}
              isPinned={(ref) => isPinned("resource", ref)}
              onToggle={(scope, category, filename, label) =>
                togglePin({
                  type: "resource",
                  ref: `${scope}/${category}/${filename}`,
                  label,
                })
              }
            />
          )}
          {active === "syllabus" && (
            <SyllabusTab
              classLevel={classLevel}
              subject={subject}
              search={search}
              isPinned={(t) => isPinned("syllabus_topic", t)}
              onToggle={(topic) =>
                togglePin({ type: "syllabus_topic", ref: topic, label: topic })
              }
            />
          )}
        </div>

        {/* Footer */}
        <footer className="border-t border-gray-200 px-5 py-3 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-sm border border-gray-300 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(pinned)}
            className="px-4 py-1.5 rounded text-sm bg-purple-700 hover:bg-purple-800 text-white font-medium"
          >
            Save · {pinned.length} pinned
          </button>
        </footer>
      </div>
    </div>
  );
}

// ───────────── tab bodies ─────────────

function LibraryTab({
  childId,
  search,
  isPinned,
  onToggle,
}: {
  childId: number;
  search: string;
  isPinned: (id: number) => boolean;
  onToggle: (file: LibraryFile) => void;
}) {
  // Fetch all library entries (kid-scoped + global). The library tracks
  // child_id as nullable so files w/o a kid still apply.
  const { data: rows, isLoading } = useQuery({
    queryKey: ["library-list-for-picker", childId],
    queryFn: () => api.libraryList(),
  });
  const filtered = useMemo(() => {
    if (!rows) return [];
    const s = search.toLowerCase();
    return rows.filter((f) => {
      if (!s) return true;
      return (
        (f.original_filename || f.filename || "").toLowerCase().includes(s) ||
        (f.llm_summary || "").toLowerCase().includes(s) ||
        (f.llm_subject || "").toLowerCase().includes(s) ||
        (f.llm_keywords || []).some((k) => k.toLowerCase().includes(s))
      );
    });
  }, [rows, search]);

  if (isLoading) return <div className="text-sm text-gray-500 italic">Loading library…</div>;
  if (!rows || rows.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic">
        No library files yet. Upload textbooks / PDFs from the Library page,
        then come back to pin them.
      </div>
    );
  }
  if (filtered.length === 0) {
    return <div className="text-sm text-gray-500 italic">No matches.</div>;
  }
  return (
    <ul className="space-y-1.5">
      {filtered.map((f) => (
        <li key={f.id}>
          <button
            type="button"
            onClick={() => onToggle(f)}
            className={
              "w-full text-left px-3 py-2 rounded border flex items-start gap-2 " +
              (isPinned(f.id)
                ? "border-purple-400 bg-purple-50"
                : "border-gray-200 hover:bg-gray-50")
            }
          >
            <span className="text-lg shrink-0 mt-0.5">{libIcon(f.mime_type)}</span>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-sm truncate">
                {f.original_filename || f.filename}
              </div>
              <div className="text-xs text-gray-500 flex flex-wrap gap-1.5 mt-0.5">
                {f.llm_kind && <span className="chip-purple">{f.llm_kind}</span>}
                {f.llm_subject && <span className="chip-blue">{f.llm_subject}</span>}
                {f.llm_class_level !== null && f.llm_class_level !== undefined && (
                  <span className="chip-gray">class {f.llm_class_level}</span>
                )}
                {f.size_bytes ? (
                  <span className="text-gray-400">
                    {(f.size_bytes / (1024 * 1024)).toFixed(1)} MB
                  </span>
                ) : null}
              </div>
              {f.llm_summary && (
                <div className="text-xs text-gray-600 mt-0.5 line-clamp-2">
                  {f.llm_summary}
                </div>
              )}
            </div>
            {isPinned(f.id) ? (
              <span className="text-purple-700 text-sm">✓ pinned</span>
            ) : (
              <span className="text-gray-300 text-sm">+</span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}

function ResourcesTab({
  childId,
  search,
  isPinned,
  onToggle,
}: {
  childId: number;
  search: string;
  isPinned: (ref: string) => boolean;
  onToggle: (scope: string, category: string, filename: string, label: string) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["resources-for-picker", childId],
    queryFn: () => api.resources(childId),
  });

  type Row = { scope: string; category: string; file: ResourceFile };
  const rows = useMemo<Row[]>(() => {
    if (!data) return [];
    const out: Row[] = [];
    for (const cat of Object.keys(data.schoolwide || {})) {
      for (const f of data.schoolwide[cat] || []) {
        out.push({ scope: "schoolwide", category: cat, file: f });
      }
    }
    for (const k of data.kids || []) {
      if (k.child_id !== childId) continue;
      for (const cat of Object.keys(k.by_category || {})) {
        for (const f of k.by_category[cat] || []) {
          out.push({ scope: "kid", category: cat, file: f });
        }
      }
    }
    return out;
  }, [data, childId]);

  const filtered = useMemo(() => {
    const s = search.toLowerCase();
    if (!s) return rows;
    return rows.filter(
      (r) =>
        r.file.filename.toLowerCase().includes(s) ||
        r.category.toLowerCase().includes(s),
    );
  }, [rows, search]);

  if (isLoading) return <div className="text-sm text-gray-500 italic">Loading resources…</div>;
  if (rows.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic">
        No portal-harvested resources for this kid yet. Run the heavy-tier
        sync from Settings to populate them.
      </div>
    );
  }
  if (filtered.length === 0) {
    return <div className="text-sm text-gray-500 italic">No matches.</div>;
  }
  // Group by category for cleaner display.
  const byCategory = new Map<string, Row[]>();
  for (const r of filtered) {
    const key = `${r.scope === "kid" ? "Per-kid · " : ""}${r.category}`;
    if (!byCategory.has(key)) byCategory.set(key, []);
    byCategory.get(key)!.push(r);
  }
  const grouped = Array.from(byCategory.entries()).sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="space-y-3">
      {grouped.map(([cat, items]) => (
        <section key={cat}>
          <h4 className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">
            {cat}
          </h4>
          <ul className="space-y-1">
            {items.map((r) => {
              const ref = `${r.scope}/${r.category}/${r.file.filename}`;
              const pinned = isPinned(ref);
              return (
                <li key={ref}>
                  <button
                    type="button"
                    onClick={() =>
                      onToggle(r.scope, r.category, r.file.filename, r.file.filename)
                    }
                    className={
                      "w-full text-left px-3 py-1.5 rounded border flex items-center gap-2 " +
                      (pinned
                        ? "border-purple-400 bg-purple-50"
                        : "border-gray-200 hover:bg-gray-50")
                    }
                  >
                    <span className="text-base shrink-0">📄</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{r.file.filename}</div>
                      <div className="text-[10px] text-gray-400">
                        {r.scope === "kid" ? "kid · " : "schoolwide · "}
                        {r.file.size_bytes
                          ? `${(r.file.size_bytes / 1024).toFixed(1)} KB`
                          : ""}
                      </div>
                    </div>
                    <span className={pinned ? "text-purple-700 text-sm" : "text-gray-300 text-sm"}>
                      {pinned ? "✓" : "+"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

function SyllabusTab({
  classLevel,
  subject,
  search,
  isPinned,
  onToggle,
}: {
  classLevel: number | null;
  subject: string;
  search: string;
  isPinned: (topic: string) => boolean;
  onToggle: (topic: string) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["syllabus-for-picker", classLevel],
    queryFn: () => api.syllabus(classLevel!),
    enabled: classLevel !== null,
  });
  if (classLevel === null) {
    return <div className="text-sm text-gray-500 italic">No class level on file for this kid.</div>;
  }
  if (isLoading) return <div className="text-sm text-gray-500 italic">Loading syllabus…</div>;
  if (!data) return <div className="text-sm text-gray-500 italic">No syllabus found.</div>;

  const s = search.toLowerCase();
  const cycles = data.cycles || [];
  return (
    <div className="space-y-3">
      {cycles.map((cyc) => {
        const topicsForSubject = cyc.topics_by_subject[subject] || [];
        const filtered = s
          ? topicsForSubject.filter((t) => t.toLowerCase().includes(s))
          : topicsForSubject;
        if (filtered.length === 0) return null;
        return (
          <section key={cyc.name}>
            <h4 className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">
              {cyc.name} <span className="opacity-60">· {cyc.start} → {cyc.end}</span>
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {filtered.map((t) => {
                const pinned = isPinned(t);
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => onToggle(t)}
                    className={
                      "text-xs px-2 py-1 rounded-full border " +
                      (pinned
                        ? "border-purple-400 bg-purple-100 text-purple-900 font-medium"
                        : "border-gray-300 text-gray-700 hover:bg-gray-50")
                    }
                  >
                    {pinned ? "✓ " : ""}{t}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
      {cycles.every((c) => (c.topics_by_subject[subject] || []).length === 0) && (
        <div className="text-sm text-gray-500 italic">
          No topics for {subject} in any cycle. Try the syllabus settings page.
        </div>
      )}
    </div>
  );
}

// ───────────── helpers ─────────────

function tabLabel(t: TabId): string {
  return t === "library" ? "Library" : t === "resources" ? "Resources" : "Syllabus";
}

function tabEmoji(t: TabId): string {
  return t === "library" ? "📚" : t === "resources" ? "📁" : "🎯";
}

function typeIcon(t: PinnedSourceType): string {
  return t === "library" ? "📚" : t === "resource" ? "📁" : "🎯";
}

function libIcon(mime: string | null): string {
  if (!mime) return "📄";
  if (mime === "application/pdf") return "📕";
  if (mime === "application/epub+zip") return "📘";
  if (mime.startsWith("image/")) return "🖼️";
  if (mime.includes("word")) return "📝";
  if (mime.includes("sheet") || mime.includes("excel")) return "📊";
  return "📄";
}

function labelForLibrary(f: LibraryFile): string {
  const stem = (f.original_filename || f.filename || "").split("/").pop() || "untitled";
  return stem.length > 60 ? stem.slice(0, 58) + "…" : stem;
}
