import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, Assignment } from "../api";
import StatusPopover from "../components/StatusPopover";
import AuditDrawer from "../components/AuditDrawer";
import ChildHeader from "../components/ChildHeader";
import BulkActionBar from "../components/BulkActionBar";
import { AssignmentList } from "../components/AssignmentList";
import { useSelection } from "../components/useSelection";
import { useUiPrefs } from "../components/useUiPrefs";

/** Sort keys — mapped to the row's logical columns. The grid lays
 *  out as [select | subject | title | due | status], so the header
 *  strip uses the same template and clicking a header cycles through
 *  ascending → descending → unsorted (back to whatever the API
 *  returned, which is roughly newest-first). */
type SortKey =
  | "subject"
  | "title"
  | "due_or_date"
  | "priority"
  | "effective_status"
  | "first_seen_at"
  | null;
type SortDir = "asc" | "desc";

const STATUS_ORDER: Record<string, number> = {
  overdue: 0,
  pending: 1,
  due_today: 1,
  needs_help: 2,
  blocked: 3,
  in_progress: 4,
  done_at_home: 5,
  submitted: 6,
  graded: 7,
  skipped: 8,
};

function compare(a: Assignment, b: Assignment, key: NonNullable<SortKey>): number {
  if (key === "priority") {
    return (a.priority || 0) - (b.priority || 0);
  }
  if (key === "effective_status") {
    const av = STATUS_ORDER[a.effective_status || ""] ?? 99;
    const bv = STATUS_ORDER[b.effective_status || ""] ?? 99;
    return av - bv;
  }
  // String / date columns. Empty strings sort last in asc.
  const av = (a[key] as string | null | undefined) ?? "";
  const bv = (b[key] as string | null | undefined) ?? "";
  if (av === "" && bv !== "") return 1;
  if (bv === "" && av !== "") return -1;
  return av.localeCompare(bv);
}

export default function ChildAssignments() {
  const { id } = useParams();
  const childId = Number(id);
  const [status, setStatus] = useState<string>("");
  const [subject, setSubject] = useState<string>("");
  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [audit, setAudit] = useState<Assignment | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("due_or_date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const selection = useSelection();
  const prefs = useUiPrefs();

  const { data } = useQuery({
    queryKey: ["assignments", childId, status, subject],
    queryFn: () => api.assignments({ child_id: childId, status: status || undefined, subject: subject || undefined }),
    enabled: !isNaN(childId),
  });

  const rows = data || [];
  const subjects = Array.from(new Set(rows.map((r) => r.subject).filter(Boolean))) as string[];

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const out = [...rows].sort((a, b) => compare(a, b, sortKey));
    return sortDir === "desc" ? out.reverse() : out;
  }, [rows, sortKey, sortDir]);

  // Click a column → cycle: same-column-asc → same-column-desc →
  // different-column-asc. Clicking a different column starts asc.
  const cycleSort = (k: NonNullable<SortKey>) => {
    if (sortKey !== k) {
      setSortKey(k);
      setSortDir("asc");
      return;
    }
    if (sortDir === "asc") {
      setSortDir("desc");
      return;
    }
    // Was desc on this col → clear sort entirely (back to API order).
    setSortKey(null);
    setSortDir("asc");
  };

  return (
    <div>
      <ChildHeader title="All assignments" />
      <div className="flex items-center gap-3 mb-3 text-sm flex-wrap">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1"
        >
          <option value="">All statuses</option>
          <option value="overdue">Overdue</option>
          <option value="submitted">Submitted</option>
          <option value="graded">Graded</option>
          <option value="parent_submitted">Parent-marked submitted</option>
        </select>
        <select
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1"
        >
          <option value="">All subjects</option>
          {subjects.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="text-gray-500">{rows.length} rows</div>
        {sortKey && (
          <button
            type="button"
            onClick={() => setSortKey(null)}
            className="text-xs text-blue-700 hover:underline"
            title="Clear sort, restore API order"
          >
            clear sort
          </button>
        )}
      </div>

      <section className="surface overflow-hidden">
        {/* Sortable column-header strip — mirrors the row's grid
            template so headers line up exactly with their columns.
            See `.row { grid-template-columns: 20px 7rem 1fr 7rem 8rem }`
            in styles.css. */}
        <div
          className="grid items-center gap-3 px-3 py-2 text-[11px] uppercase tracking-wider font-semibold text-gray-500 bg-[color:var(--bg-muted)] border-b border-[color:var(--line)] select-none"
          style={{ gridTemplateColumns: "20px 7rem 1fr 7rem 8rem" }}
        >
          <span aria-hidden></span>
          <SortHeader
            label="Subject"
            active={sortKey === "subject"}
            dir={sortDir}
            onClick={() => cycleSort("subject")}
          />
          <SortHeader
            label="Title"
            active={sortKey === "title"}
            dir={sortDir}
            onClick={() => cycleSort("title")}
          />
          <SortHeader
            label="Due"
            active={sortKey === "due_or_date"}
            dir={sortDir}
            onClick={() => cycleSort("due_or_date")}
          />
          <SortHeader
            label="Status"
            active={sortKey === "effective_status"}
            dir={sortDir}
            onClick={() => cycleSort("effective_status")}
          />
        </div>
        <AssignmentList
          rows={sortedRows}
          label={
            sortKey
              ? `Results · sorted by ${sortKey === "due_or_date" ? "due" : sortKey === "effective_status" ? "status" : sortKey} ${sortDir === "asc" ? "↑" : "↓"}`
              : "Results"
          }
          selection={selection}
          onOpenAudit={setAudit}
          onOpenPopover={(a, r) => setPopover({ a, rect: r })}
          bucketId={`bucket-${childId}-all`}
          collapsed={prefs.isCollapsed(`bucket-${childId}-all`, false)}
          onToggleCollapsed={() => prefs.toggleCollapsed(`bucket-${childId}-all`, false)}
          flatRender={sortKey !== null}
        />
      </section>

      <BulkActionBar
        selectedIds={selection.list}
        onClear={selection.clear}
        scope="All assignments"
      />
      {popover && (
        <StatusPopover a={popover.a} anchorRect={popover.rect} onClose={() => setPopover(null)} />
      )}
      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
    </div>
  );
}

function SortHeader({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex items-center gap-1 text-left hover:text-gray-800 truncate " +
        (active ? "text-gray-900" : "")
      }
      title={`Sort by ${label.toLowerCase()}${active ? ` (${dir === "asc" ? "ascending" : "descending"} — click to ${dir === "asc" ? "reverse" : "clear"})` : ""}`}
    >
      <span>{label}</span>
      <span
        className={
          "text-[9px] " +
          (active ? "text-blue-700" : "text-gray-300")
        }
        aria-hidden
      >
        {active ? (dir === "asc" ? "▲" : "▼") : "▲▼"}
      </span>
    </button>
  );
}
