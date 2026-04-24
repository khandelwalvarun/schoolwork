import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Assignment } from "../api";
import StatusPopover from "../components/StatusPopover";
import AuditDrawer from "../components/AuditDrawer";
import ChildHeader from "../components/ChildHeader";
import BulkActionBar from "../components/BulkActionBar";
import { AssignmentList } from "../components/AssignmentList";
import { useSelection } from "../components/useSelection";
import { useUiPrefs } from "../components/useUiPrefs";

export default function ChildAssignments() {
  const { id } = useParams();
  const childId = Number(id);
  const [status, setStatus] = useState<string>("");
  const [subject, setSubject] = useState<string>("");
  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [audit, setAudit] = useState<Assignment | null>(null);
  const selection = useSelection();
  const prefs = useUiPrefs();

  const { data } = useQuery({
    queryKey: ["assignments", childId, status, subject],
    queryFn: () => api.assignments({ child_id: childId, status: status || undefined, subject: subject || undefined }),
    enabled: !isNaN(childId),
  });

  const rows = data || [];
  const subjects = Array.from(new Set(rows.map((r) => r.subject).filter(Boolean))) as string[];

  return (
    <div>
      <ChildHeader title="All assignments" />
      <div className="flex items-center gap-3 mb-3 text-sm">
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
      </div>

      <section className="surface overflow-hidden">
        <AssignmentList
          rows={rows}
          label="Results"
          selection={selection}
          onOpenAudit={setAudit}
          onOpenPopover={(a, r) => setPopover({ a, rect: r })}
          bucketId={`bucket-${childId}-all`}
          collapsed={prefs.isCollapsed(`bucket-${childId}-all`, false)}
          onToggleCollapsed={() => prefs.toggleCollapsed(`bucket-${childId}-all`, false)}
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
