import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState, useRef } from "react";
import { api, Assignment, GradeTrend, SyllabusCycle } from "../api";
import Attachments from "../components/Attachments";
import StatusPopover, { EffectiveStatusChip } from "../components/StatusPopover";
import AuditDrawer from "../components/AuditDrawer";

function PriorityStar({ n }: { n: number }) {
  if (n <= 0) return null;
  return <span className="text-amber-500 text-sm">{"★".repeat(n)}</span>;
}

function TagChips({ tags }: { tags: string[] }) {
  if (!tags || tags.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {tags.map((t) => (
        <span key={t} className="px-1.5 py-0 rounded-full border border-gray-200 bg-gray-50 text-[10px] text-gray-700">
          {t}
        </span>
      ))}
    </div>
  );
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
      title="Update status"
      className="cursor-pointer"
    >
      <EffectiveStatusChip a={a} />
    </button>
  );
}

function AssignmentRow({
  a,
  onOpenPopover,
  onOpenAudit,
}: {
  a: Assignment;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
  onOpenAudit: (a: Assignment) => void;
}) {
  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer"
        onClick={() => onOpenAudit(a)}>
      <td className="py-2 px-3 whitespace-nowrap text-gray-600 text-sm align-top">
        {a.subject}
        <PriorityStar n={a.priority} />
      </td>
      <td className="py-2 px-3 align-top">
        <div>{a.title}</div>
        {a.title_en && a.title_en !== a.title && (
          <div className="text-xs text-gray-600 italic mt-0.5">→ {a.title_en}</div>
        )}
        {a.syllabus_context && (
          <div className="text-xs text-gray-500 mt-0.5">↳ {a.syllabus_context}</div>
        )}
        <Attachments items={a.attachments} />
        <TagChips tags={a.tags} />
      </td>
      <td className="py-2 px-3 text-gray-500 text-sm whitespace-nowrap align-top">{a.normalized?.type}</td>
      <td className="py-2 px-3 whitespace-nowrap text-sm align-top">{a.due_or_date}</td>
      <td className="py-2 px-3 align-top" onClick={(e) => e.stopPropagation()}>
        <StatusChipButton a={a} onClick={(rect) => onOpenPopover(a, rect)} />
      </td>
    </tr>
  );
}

function AssignmentTable({
  title,
  rows,
  accent,
  onOpenPopover,
  onOpenAudit,
}: {
  title: string;
  rows: Assignment[];
  accent: string;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
  onOpenAudit: (a: Assignment) => void;
}) {
  if (!rows.length) return null;
  return (
    <div className="mt-4">
      <h4 className={`text-sm font-semibold ${accent}`}>{title} — {rows.length}</h4>
      <table className="w-full text-sm mt-1">
        <thead>
          <tr className="text-left text-gray-500 text-xs uppercase">
            <th className="py-1 px-3 font-medium">Subject</th>
            <th className="py-1 px-3 font-medium">Assignment</th>
            <th className="py-1 px-3 font-medium">Type</th>
            <th className="py-1 px-3 font-medium">Due</th>
            <th className="py-1 px-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <AssignmentRow key={a.id} a={a} onOpenPopover={onOpenPopover} onOpenAudit={onOpenAudit} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GradeTrendBlock({ trends }: { trends: GradeTrend[] }) {
  if (!trends || trends.length === 0) return null;
  return (
    <div className="mt-6">
      <h4 className="text-sm font-semibold text-purple-700">📊 Grade trend</h4>
      <table className="w-full text-sm mt-1">
        <tbody>
          {trends.map((t) => (
            <tr key={t.subject} className="border-t border-gray-100">
              <td className="py-1 px-3">{t.subject}</td>
              <td className="py-1 px-3 font-mono">{t.sparkline}</td>
              <td className="py-1 px-3 text-lg">{t.arrow}</td>
              <td className="py-1 px-3">latest <b>{t.latest.toFixed(0)}%</b></td>
              <td className="py-1 px-3 text-gray-500">avg {t.avg.toFixed(0)}% (n={t.count})</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CycleBadge({ cycle }: { cycle: SyllabusCycle | null }) {
  if (!cycle) return null;
  return (
    <span className="ml-2 text-xs text-purple-700 bg-purple-50 border border-purple-200 rounded px-2 py-0.5">
      📚 {cycle.name} · {cycle.start} → {cycle.end}
    </span>
  );
}

export default function Today() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["today"], queryFn: api.today });

  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [audit, setAudit] = useState<Assignment | null>(null);

  if (isLoading) return <div>Loading…</div>;
  if (error) return <div className="text-red-700">Error: {String(error)}</div>;
  if (!data) return null;

  const refresh = () => qc.invalidateQueries({ queryKey: ["today"] });
  const sync = async () => { await api.syncNow(); setTimeout(refresh, 500); };
  const sendDigest = async () => { await api.digestRun(); };

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-2xl font-bold">Today</h2>
          <div className="text-xs text-gray-500 mt-1">
            Last sync: {data.last_sync ? `${data.last_sync.status} at ${data.last_sync.ended_at || "…"}` : "never"}
          </div>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 bg-blue-700 text-white text-sm rounded hover:bg-blue-800" onClick={sync}>Sync now</button>
          <button className="px-3 py-1.5 bg-gray-700 text-white text-sm rounded hover:bg-gray-800" onClick={sendDigest}>Send digest</button>
        </div>
      </div>

      <div className="flex gap-3 mb-6">
        <span className="chip-red">🚨 Overdue: <b>{data.totals.overdue}</b></span>
        <span className="chip-amber">📌 Due today: <b>{data.totals.due_today}</b></span>
        <span className="chip-blue">📅 Upcoming: <b>{data.totals.upcoming}</b></span>
      </div>

      {data.children.map((kid) => (
        <section key={kid.child.id} className="mb-10 bg-white border border-gray-200 rounded p-5 shadow-sm">
          <div className="flex items-start justify-between border-b border-gray-100 pb-2 mb-2">
            <h3 className="text-lg font-bold">
              <Link to={`/child/${kid.child.id}`} className="hover:text-blue-700">
                {kid.child.display_name}
              </Link>
              <span className="text-gray-500"> · {kid.child.class_section}</span>
              <CycleBadge cycle={kid.syllabus_cycle} />
            </h3>
            <div className="text-xs flex gap-2 pt-1">
              <Link className="text-blue-700 hover:underline" to={`/child/${kid.child.id}/board`}>Board</Link>
              <Link className="text-blue-700 hover:underline" to={`/child/${kid.child.id}/grades`}>Grades</Link>
              <Link className="text-blue-700 hover:underline" to={`/child/${kid.child.id}/assignments`}>Assignments</Link>
              <Link className="text-blue-700 hover:underline" to={`/child/${kid.child.id}/syllabus`}>Syllabus</Link>
            </div>
          </div>
          {kid.overdue_sparkline && (
            <div className="text-xs text-gray-600 mb-3">
              14-day backlog <span className="font-mono text-base">{kid.overdue_sparkline}</span>
              <span className="ml-2 text-gray-500">now {kid.overdue_trend[kid.overdue_trend.length - 1]?.count ?? 0}</span>
            </div>
          )}
          <AssignmentTable title="🚨 Overdue" rows={kid.overdue} accent="text-red-700"
            onOpenPopover={(a, r) => setPopover({ a, rect: r })} onOpenAudit={(a) => setAudit(a)} />
          <AssignmentTable title="📌 Due today" rows={kid.due_today} accent="text-amber-700"
            onOpenPopover={(a, r) => setPopover({ a, rect: r })} onOpenAudit={(a) => setAudit(a)} />
          <AssignmentTable title="📅 Upcoming" rows={kid.upcoming} accent="text-blue-700"
            onOpenPopover={(a, r) => setPopover({ a, rect: r })} onOpenAudit={(a) => setAudit(a)} />
          <GradeTrendBlock trends={kid.grade_trends} />
        </section>
      ))}

      {data.messages_last_7d.length > 0 && (
        <section className="mb-10 bg-white border border-gray-200 rounded p-5 shadow-sm">
          <h3 className="text-lg font-bold border-b border-gray-100 pb-2 mb-3">📬 School messages (last 7 days)</h3>
          <ul className="space-y-1">
            {data.messages_last_7d.slice(0, 15).map((m) => (
              <li key={m.id} className="text-sm">
                <b>{m.title || m.subject}</b>
                <span className="text-gray-500 ml-2">{m.due_or_date}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {popover && (
        <StatusPopover a={popover.a} anchorRect={popover.rect}
          onClose={() => setPopover(null)} onSaved={refresh} />
      )}
      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
    </div>
  );
}
