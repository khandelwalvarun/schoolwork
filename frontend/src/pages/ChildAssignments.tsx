import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, Assignment } from "../api";

function StatusPill({ a }: { a: Assignment }) {
  const s = a.effective_status ?? a.status;
  const pm = !!a.parent_marked_submitted_at;
  const cls =
    s === "overdue" ? "chip-red" :
    s === "graded" ? "chip-green" :
    s === "submitted" ? "chip-blue" :
    "chip-amber";
  return <span className={cls}>{pm ? "submitted ✓" : (s || "unknown")}</span>;
}

export default function ChildAssignments() {
  const { id } = useParams();
  const childId = Number(id);
  const qc = useQueryClient();
  const [status, setStatus] = useState<string>("");
  const [subject, setSubject] = useState<string>("");

  const { data } = useQuery({
    queryKey: ["assignments", childId, status, subject],
    queryFn: () => api.assignments({ child_id: childId, status: status || undefined, subject: subject || undefined }),
    enabled: !isNaN(childId),
  });

  const toggle = async (a: Assignment) => {
    if (a.parent_marked_submitted_at) await api.unmarkSubmitted(a.id);
    else await api.markSubmitted(a.id);
    qc.invalidateQueries({ queryKey: ["assignments", childId] });
  };

  const rows = data || [];
  const subjects = Array.from(new Set(rows.map((r) => r.subject).filter(Boolean))) as string[];

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">
        <Link to={`/child/${childId}`} className="text-gray-400 hover:text-gray-700">← </Link>
        All assignments
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
            <th className="py-2 px-3"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id} className="border-t border-gray-100 align-top">
              <td className="py-2 px-3 text-gray-600 whitespace-nowrap">{a.subject}</td>
              <td className="py-2 px-3">
                {a.title}
                {a.title_en && a.title_en !== a.title && (
                  <div className="text-xs text-gray-600 italic mt-0.5">→ {a.title_en}</div>
                )}
              </td>
              <td className="py-2 px-3 whitespace-nowrap">{a.due_or_date}</td>
              <td className="py-2 px-3"><StatusPill a={a} /></td>
              <td className="py-2 px-3 text-xs text-gray-500">{a.syllabus_context ?? "—"}</td>
              <td className="py-2 px-3">
                <button
                  onClick={() => toggle(a)}
                  className="text-xs px-2 py-0.5 border border-gray-300 rounded hover:bg-gray-50"
                >
                  {a.parent_marked_submitted_at ? "Undo" : "✓ Submitted"}
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="py-4 text-center text-gray-400">No assignments match.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
