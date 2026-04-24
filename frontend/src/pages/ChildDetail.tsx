import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, Assignment, GradeTrend } from "../api";
import Attachments from "../components/Attachments";
import TitleBlock from "../components/TitleBlock";
import AuditDrawer from "../components/AuditDrawer";
import StatusPopover, { EffectiveStatusChip } from "../components/StatusPopover";
import ChildHeader from "../components/ChildHeader";

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
      title="Click to update status"
      className="cursor-pointer"
    >
      <EffectiveStatusChip a={a} />
    </button>
  );
}

function Row({
  a,
  onOpenAudit,
  onOpenPopover,
}: {
  a: Assignment;
  onOpenAudit: (a: Assignment) => void;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
}) {
  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer" onClick={() => onOpenAudit(a)}>
      <td className="py-1 px-2 text-gray-600 text-sm whitespace-nowrap align-top">
        {a.subject}
        {a.priority > 0 && <span className="ml-1 text-amber-500 text-xs">{"★".repeat(a.priority)}</span>}
      </td>
      <td className="py-1 px-2 align-top">
        <TitleBlock title={a.title} titleEn={a.title_en} className="text-sm" />
        {a.syllabus_context && (
          <div className="text-xs text-gray-500 mt-0.5">↳ {a.syllabus_context}</div>
        )}
        <Attachments items={a.attachments} />
      </td>
      <td className="py-1 px-2 text-sm whitespace-nowrap align-top">{a.due_or_date}</td>
      <td className="py-1 px-2 align-top" onClick={(e) => e.stopPropagation()}>
        <StatusChipButton a={a} onClick={(r) => onOpenPopover(a, r)} />
      </td>
    </tr>
  );
}

export default function ChildDetail() {
  const { id } = useParams();
  const childId = Number(id);
  const [audit, setAudit] = useState<Assignment | null>(null);
  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["child-detail", childId],
    queryFn: () => api.childDetail(childId),
    enabled: !isNaN(childId),
  });
  if (isLoading) return <div>Loading…</div>;
  if (error) return <div className="text-red-700">Error: {String(error)}</div>;
  if (!data) return null;
  const c = data.child;
  return (
    <div>
      <ChildHeader title={c.display_name} />
      <div className="text-gray-500 text-sm mb-4 -mt-2">
        Class {c.class_level}{c.class_section ? ` · ${c.class_section}` : ""}
        {data.syllabus_cycle && (
          <span className="ml-3 text-purple-700 bg-purple-50 border border-purple-200 rounded px-2 py-0.5 text-xs">
            📚 {data.syllabus_cycle.name} · {data.syllabus_cycle.start} → {data.syllabus_cycle.end}
          </span>
        )}
      </div>

      <div className="flex gap-3 mb-6">
        <span className="chip-red">🚨 Overdue: <b>{data.counts.overdue}</b></span>
        <span className="chip-amber">📌 Due today: <b>{data.counts.due_today}</b></span>
        <span className="chip-blue">📅 Upcoming: <b>{data.counts.upcoming}</b></span>
        <span className="chip-amber">💬 Comments: <b>{data.counts.comments}</b></span>
      </div>

      {data.overdue_sparkline && (
        <div className="mb-6 bg-white border border-gray-200 rounded p-4">
          <div className="text-sm text-gray-600 mb-1">14-day overdue backlog</div>
          <div className="font-mono text-xl tracking-wide">{data.overdue_sparkline}</div>
          <div className="text-xs text-gray-500 mt-1">
            {data.overdue_trend[0]?.date} → {data.overdue_trend[data.overdue_trend.length - 1]?.date}
            &nbsp;· now {data.overdue_trend[data.overdue_trend.length - 1]?.count}
          </div>
        </div>
      )}

      {data.overdue.length > 0 && (
        <section className="mb-6 bg-white border border-gray-200 rounded shadow-sm p-4">
          <h3 className="font-semibold text-red-700 mb-2">Overdue — {data.overdue.length}</h3>
          <table className="w-full text-sm"><tbody>{data.overdue.map((a) => (
            <Row key={a.id} a={a} onOpenAudit={setAudit}
              onOpenPopover={(x, r) => setPopover({ a: x, rect: r })} />
          ))}</tbody></table>
        </section>
      )}
      {data.due_today.length > 0 && (
        <section className="mb-6 bg-white border border-gray-200 rounded shadow-sm p-4">
          <h3 className="font-semibold text-amber-700 mb-2">Due today — {data.due_today.length}</h3>
          <table className="w-full text-sm"><tbody>{data.due_today.map((a) => (
            <Row key={a.id} a={a} onOpenAudit={setAudit}
              onOpenPopover={(x, r) => setPopover({ a: x, rect: r })} />
          ))}</tbody></table>
        </section>
      )}
      {data.upcoming.length > 0 && (
        <section className="mb-6 bg-white border border-gray-200 rounded shadow-sm p-4">
          <h3 className="font-semibold text-blue-700 mb-2">Upcoming — {data.upcoming.length}</h3>
          <table className="w-full text-sm"><tbody>{data.upcoming.slice(0, 20).map((a) => (
            <Row key={a.id} a={a} onOpenAudit={setAudit}
              onOpenPopover={(x, r) => setPopover({ a: x, rect: r })} />
          ))}</tbody></table>
        </section>
      )}

      {data.grade_trends.length > 0 && (
        <section className="mb-6 bg-white border border-gray-200 rounded shadow-sm p-4">
          <h3 className="font-semibold text-purple-700 mb-2">📊 Grade trends</h3>
          <table className="w-full text-sm"><tbody>
            {data.grade_trends.map((t: GradeTrend) => (
              <tr key={t.subject} className="border-t border-gray-100">
                <td className="py-1 px-2">{t.subject}</td>
                <td className="py-1 px-2 font-mono">{t.sparkline}</td>
                <td className="py-1 px-2 text-lg">{t.arrow}</td>
                <td className="py-1 px-2">latest <b>{t.latest.toFixed(0)}%</b></td>
                <td className="py-1 px-2 text-gray-500">avg {t.avg.toFixed(0)}% (n={t.count})</td>
              </tr>
            ))}
          </tbody></table>
          <div className="mt-2 text-xs">
            <Link className="text-blue-700 hover:underline" to={`/child/${childId}/grades`}>See full grades →</Link>
          </div>
        </section>
      )}

      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
      {popover && (
        <StatusPopover a={popover.a} anchorRect={popover.rect}
          onClose={() => setPopover(null)} />
      )}
    </div>
  );
}
