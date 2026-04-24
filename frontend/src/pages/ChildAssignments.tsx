import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, Assignment } from "../api";
import StatusPopover, { EffectiveStatusChip } from "../components/StatusPopover";
import AuditDrawer from "../components/AuditDrawer";

function PriorityStar({ n }: { n: number }) {
  if (n <= 0) return null;
  return <span className="ml-2 text-amber-500 text-xs">{"★".repeat(n)}</span>;
}

function StatusChipButton({ a, onClick }: { a: Assignment; onClick: (rect: DOMRect) => void }) {
  const ref = useRef<HTMLButtonElement | null>(null);
  return (
    <button
      ref={ref}
      onClick={(e) => {
        e.stopPropagation();
        const rect = (ref.current as HTMLButtonElement).getBoundingClientRect();
        onClick(rect);
      }}
    >
      <EffectiveStatusChip a={a} />
    </button>
  );
}

export default function ChildAssignments() {
  const { id } = useParams();
  const childId = Number(id);
  const [status, setStatus] = useState<string>("");
  const [subject, setSubject] = useState<string>("");
  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [audit, setAudit] = useState<Assignment | null>(null);

  const { data } = useQuery({
    queryKey: ["assignments", childId, status, subject],
    queryFn: () => api.assignments({ child_id: childId, status: status || undefined, subject: subject || undefined }),
    enabled: !isNaN(childId),
  });

  const rows = data || [];
  const subjects = Array.from(new Set(rows.map((r) => r.subject).filter(Boolean))) as string[];

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">
        <Link to={`/child/${childId}`} className="text-gray-400 hover:text-gray-700">← </Link>
        All assignments
        <Link to={`/child/${childId}/board`} className="ml-4 text-sm text-blue-700 hover:underline font-normal">Open kanban →</Link>
      </h2>
      <div className="flex gap-3 mb-4 text-sm">
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
        <div className="text-gray-500 self-center">{rows.length} rows</div>
      </div>
      <table className="w-full text-sm bg-white border border-gray-200 rounded shadow-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-gray-500 border-b border-gray-100">
            <th className="py-2 px-3">Subject</th>
            <th className="py-2 px-3">Title</th>
            <th className="py-2 px-3">Due</th>
            <th className="py-2 px-3">Status</th>
            <th className="py-2 px-3">Syllabus</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id} className="border-t border-gray-100 hover:bg-gray-50 align-top cursor-pointer"
                onClick={() => setAudit(a)}>
              <td className="py-2 px-3 text-gray-600 whitespace-nowrap">
                {a.subject}
                <PriorityStar n={a.priority} />
              </td>
              <td className="py-2 px-3">
                {a.title}
                {a.title_en && a.title_en !== a.title && (
                  <div className="text-xs text-gray-600 italic mt-0.5">→ {a.title_en}</div>
                )}
                {a.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {a.tags.map((t) => (
                      <span key={t} className="px-1.5 py-0 rounded-full border border-gray-200 bg-gray-50 text-[10px] text-gray-700">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </td>
              <td className="py-2 px-3 whitespace-nowrap">{a.due_or_date}</td>
              <td className="py-2 px-3" onClick={(e) => e.stopPropagation()}>
                <StatusChipButton a={a} onClick={(rect) => setPopover({ a, rect })} />
              </td>
              <td className="py-2 px-3 text-xs text-gray-500">{a.syllabus_context ?? "—"}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={5} className="py-4 text-center text-gray-400">No assignments match.</td></tr>
          )}
        </tbody>
      </table>

      {popover && (
        <StatusPopover a={popover.a} anchorRect={popover.rect}
          onClose={() => setPopover(null)} />
      )}
      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
    </div>
  );
}
