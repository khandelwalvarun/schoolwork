/**
 * Sidebar — the Linear/Notion left-rail nav.
 *
 * Layout (per the UI research synthesis):
 *
 *   ┌─────────────────────────┐
 *   │ 🎓  Parent Cockpit      │
 *   │ ─────────────────────── │
 *   │ Today                   │
 *   │ Notifications           │
 *   │ Messages                │
 *   │ ─────────────────────── │
 *   │ ▾ Tejas · 6B            │
 *   │     Overview            │
 *   │     Board               │
 *   │     Assignments         │
 *   │     Grades              │
 *   │     Comments            │
 *   │     Syllabus            │
 *   │ ▾ Samarth · 4C          │
 *   │     …                   │
 *   │ ─────────────────────── │
 *   │ School-wide             │
 *   │   Files                 │
 *   │   Resources             │
 *   │   Spelling              │
 *   │ ─────────────────────── │
 *   │ Personal                │
 *   │   Notes                 │
 *   │   Summaries             │
 *   │ ─────────────────────── │
 *   │ Settings                │
 *   │ ?  Shortcuts            │
 *   └─────────────────────────┘
 *
 * Per-kid sub-tree is collapsible (Notion-style) with state persisted in
 * uiPrefs.collapsed under key `sidebar:kid:<id>`. Default: expanded.
 *
 * Width: 224 px fixed (Notion's measure). Uses the `--bg-muted` token so
 * the sidebar recedes (Linear's "chrome darker than content" lever).
 */
import { Link, NavLink } from "react-router-dom";
import { Child } from "../api";
import { Icon } from "./Icon";
import { useUiPrefs } from "./useUiPrefs";

type Props = {
  children: Child[];
  onOpenSearch: () => void;
  onOpenHelp: () => void;
};

function navClass({ isActive }: { isActive: boolean }): string {
  return (
    "flex items-center gap-2 px-2.5 py-1.5 rounded text-sm transition-colors " +
    (isActive
      ? "bg-white text-gray-900 font-medium shadow-sm"
      : "text-gray-700 hover:bg-white/60")
  );
}

function subNavClass({ isActive }: { isActive: boolean }): string {
  return (
    "block pl-8 pr-2 py-1 text-[13px] rounded transition-colors " +
    (isActive
      ? "bg-white text-blue-700 font-medium"
      : "text-gray-600 hover:text-gray-900 hover:bg-white/60")
  );
}

const SECTION_HEAD = "px-2.5 pt-3 pb-1 text-[10px] uppercase tracking-wider text-gray-500 font-semibold";

export function Sidebar({ children, onOpenSearch, onOpenHelp }: Props) {
  const { isCollapsed, toggleCollapsed } = useUiPrefs();
  return (
    <aside
      role="navigation"
      aria-label="Primary"
      className="hidden md:flex flex-col w-56 shrink-0 bg-[color:var(--bg-muted)] border-r border-[color:var(--line)] sticky top-0 h-screen overflow-y-auto"
    >
      <div className="px-3 py-3 flex items-center gap-2 border-b border-[color:var(--line)]">
        <Link to="/" className="flex items-center gap-2 font-bold tracking-tight text-gray-900">
          <Icon name="Logo" size={20} strokeWidth={2} className="text-blue-700" />
          <span>Parent Cockpit</span>
        </Link>
      </div>

      <button
        onClick={onOpenSearch}
        className="mx-2 mt-3 mb-1 inline-flex items-center justify-between px-2.5 py-1.5 rounded
                   bg-white border border-[color:var(--line)] text-sm text-gray-500 hover:text-gray-800"
      >
        <span className="inline-flex items-center gap-2">
          <Icon name="Search" size={14} />
          <span>Search…</span>
        </span>
        <span className="kbd">⌘K</span>
      </button>

      <nav className="px-2 py-2 flex-1 flex flex-col gap-0.5">
        <NavLink to="/" end className={navClass}>
          <Icon name="Calendar" size={16} className="text-gray-500" /> Today
        </NavLink>
        <NavLink to="/notifications" className={navClass}>
          <Icon name="Bell" size={16} className="text-gray-500" /> Notifications
        </NavLink>
        <NavLink to="/messages" className={navClass}>
          <Icon name="Inbox" size={16} className="text-gray-500" /> Messages
        </NavLink>

        {children.map((c) => {
          const collapseId = `sidebar:kid:${c.id}`;
          const collapsed = isCollapsed(collapseId, /*defaultCollapsed=*/ false);
          const tag = c.class_section ? ` · ${c.class_section}` : "";
          return (
            <div key={c.id} className="mt-2">
              <button
                onClick={() => toggleCollapsed(collapseId, false)}
                className="w-full flex items-center gap-1 px-2.5 py-1.5 text-sm text-gray-700 hover:bg-white/60 rounded"
                aria-expanded={!collapsed}
              >
                <span className={"text-gray-400 transition-transform inline-block " + (collapsed ? "" : "rotate-90")} aria-hidden>
                  ▶
                </span>
                <span className="font-semibold">{c.display_name}</span>
                <span className="text-gray-500 text-xs">{tag}</span>
              </button>
              {!collapsed && (
                <div>
                  <NavLink to={`/child/${c.id}`} end className={subNavClass}>Overview</NavLink>
                  <NavLink to={`/child/${c.id}/board`} className={subNavClass}>Board</NavLink>
                  <NavLink to={`/child/${c.id}/assignments`} className={subNavClass}>Assignments</NavLink>
                  <NavLink to={`/child/${c.id}/grades`} className={subNavClass}>Grades</NavLink>
                  <NavLink to={`/child/${c.id}/comments`} className={subNavClass}>Comments</NavLink>
                  <NavLink to={`/child/${c.id}/syllabus`} className={subNavClass}>Syllabus</NavLink>
                </div>
              )}
            </div>
          );
        })}

        <div className={SECTION_HEAD}>School-wide</div>
        <NavLink to="/attachments" className={navClass}>
          <Icon name="Files" size={16} className="text-gray-500" /> Files
        </NavLink>
        <NavLink to="/resources" className={navClass}>
          <Icon name="Library" size={16} className="text-gray-500" /> Resources
        </NavLink>
        <NavLink to="/library" className={navClass}>
          <Icon name="Library" size={16} className="text-gray-500" /> Library
        </NavLink>
        <NavLink to="/events" className={navClass}>
          <Icon name="Library" size={16} className="text-gray-500" /> Events
        </NavLink>
        <NavLink to="/mindspark" className={navClass}>
          <Icon name="Library" size={16} className="text-gray-500" /> Mindspark
        </NavLink>
        <NavLink to="/spellbee" className={navClass}>
          <Icon name="Spelling" size={16} className="text-gray-500" /> Spelling
        </NavLink>

        <div className={SECTION_HEAD}>Personal</div>
        <NavLink to="/notes" className={navClass}>
          <Icon name="Notes" size={16} className="text-gray-500" /> Notes
        </NavLink>
        <NavLink to="/summaries" className={navClass}>
          <Icon name="Library" size={16} className="text-gray-500" /> Summaries
        </NavLink>
      </nav>

      <div className="px-2 py-2 border-t border-[color:var(--line)] flex items-center justify-between">
        <NavLink to="/settings" className={navClass}>
          <Icon name="Settings" size={16} className="text-gray-500" /> Settings
        </NavLink>
        <button
          onClick={onOpenHelp}
          aria-label="Help"
          title="Keyboard shortcuts (?)"
          className="w-7 h-7 inline-flex items-center justify-center rounded text-gray-500 hover:bg-white/60"
        >
          <Icon name="Help" size={16} />
        </button>
      </div>
    </aside>
  );
}
