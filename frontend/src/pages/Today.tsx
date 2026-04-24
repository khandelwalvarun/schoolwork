import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { api, Assignment, GradeTrend, SyllabusCycle } from "../api";
import AuditDrawer from "../components/AuditDrawer";
import StatusPopover from "../components/StatusPopover";
import BulkActionBar from "../components/BulkActionBar";
import Attachments from "../components/Attachments";
import { AssignmentList } from "../components/AssignmentList";
import { useSelection } from "../components/useSelection";

function HeroBand({
  totals,
  lastSyncLabel,
  onSync,
  onSendDigest,
}: {
  totals: { overdue: number; due_today: number; upcoming: number };
  lastSyncLabel: string;
  onSync: () => void;
  onSendDigest: () => void;
}) {
  return (
    <section className="mb-6">
      <div className="flex items-end justify-between mb-3">
        <div>
          <h2 className="text-2xl font-bold">Today</h2>
          <div className="text-xs text-gray-500 mt-0.5">Last sync: {lastSyncLabel}</div>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50" onClick={onSync}>
            Sync
          </button>
          <button className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50" onClick={onSendDigest}>
            Send digest
          </button>
        </div>
      </div>
      <div className="surface p-5 flex items-center gap-10">
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Overdue</div>
          <div className="text-4xl font-bold text-red-700 leading-tight">{totals.overdue}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Due today</div>
          <div className="text-4xl font-bold text-amber-700 leading-tight">{totals.due_today}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Upcoming · 14 days</div>
          <div className="text-4xl font-bold text-blue-700 leading-tight">{totals.upcoming}</div>
        </div>
      </div>
    </section>
  );
}

function KidBacklog({ sparkline, latest }: { sparkline: string; latest: number }) {
  if (!sparkline) return null;
  return (
    <div className="text-xs text-gray-600 flex items-center gap-2">
      <span>14-day backlog</span>
      <span className="font-mono text-lg tracking-wide">{sparkline}</span>
      <span className="text-gray-500">now {latest}</span>
    </div>
  );
}

function GradeTrendsMini({ trends }: { trends: GradeTrend[] }) {
  if (!trends || trends.length === 0) return null;
  return (
    <div className="mt-3 px-3 py-2 bg-[color:var(--bg-muted)] border-t border-[color:var(--line-soft)]">
      <div className="h-section mb-1 text-purple-700">Grade trend</div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {trends.map((t) => {
          const arrowColor =
            t.arrow === "↑" ? "text-emerald-700"
          : t.arrow === "↓" ? "text-red-700"
          : "text-gray-500";
          return (
            <div key={t.subject} className="flex items-center gap-2 whitespace-nowrap">
              <span className="text-gray-700">{t.subject}</span>
              <span className="font-mono">{t.sparkline}</span>
              <span className={arrowColor}>{t.arrow}</span>
              <span className="text-gray-500">{t.latest.toFixed(0)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CycleBadge({ cycle }: { cycle: SyllabusCycle | null }) {
  if (!cycle) return null;
  return (
    <span className="chip-purple">
      {cycle.name} · {cycle.start} → {cycle.end}
    </span>
  );
}

export default function Today() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["today"], queryFn: api.today });
  const selection = useSelection();
  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [audit, setAudit] = useState<Assignment | null>(null);

  if (isLoading) return <div className="text-gray-500">Loading…</div>;
  if (error) return <div className="text-red-700">Error: {String(error)}</div>;
  if (!data) return null;

  const refresh = () => qc.invalidateQueries({ queryKey: ["today"] });
  const sync = async () => { await api.syncNow(); setTimeout(refresh, 500); };
  const sendDigest = async () => { await api.digestRun(); };

  const lastSyncLabel = data.last_sync
    ? `${data.last_sync.status} · ${data.last_sync.ended_at?.slice(0, 16).replace("T", " ") || "…"}`
    : "never";

  return (
    <div>
      <HeroBand
        totals={data.totals}
        lastSyncLabel={lastSyncLabel}
        onSync={sync}
        onSendDigest={sendDigest}
      />

      {data.children.map((kid) => (
        <section key={kid.child.id} className="surface mb-6 overflow-hidden">
          <header className="px-4 py-3 border-b border-[color:var(--line)] flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3">
              <Link to={`/child/${kid.child.id}`} className="text-lg font-semibold hover:text-blue-700">
                {kid.child.display_name}
              </Link>
              <span className="text-sm text-gray-500">· {kid.child.class_section}</span>
              <CycleBadge cycle={kid.syllabus_cycle} />
            </div>
            <div className="flex items-center gap-4">
              <KidBacklog sparkline={kid.overdue_sparkline}
                latest={kid.overdue_trend[kid.overdue_trend.length - 1]?.count ?? 0} />
              <nav className="text-xs text-gray-500 flex gap-3">
                <Link to={`/child/${kid.child.id}/board`} className="hover:text-blue-700">Board</Link>
                <Link to={`/child/${kid.child.id}/assignments`} className="hover:text-blue-700">All</Link>
                <Link to={`/child/${kid.child.id}/grades`} className="hover:text-blue-700">Grades</Link>
                <Link to={`/child/${kid.child.id}/syllabus`} className="hover:text-blue-700">Syllabus</Link>
              </nav>
            </div>
          </header>

          <AssignmentList
            rows={kid.overdue}
            label="Overdue"
            tone="red"
            selection={selection}
            onOpenAudit={setAudit}
            onOpenPopover={(a, r) => setPopover({ a, rect: r })}
          />
          <AssignmentList
            rows={kid.due_today}
            label="Due today"
            tone="amber"
            selection={selection}
            onOpenAudit={setAudit}
            onOpenPopover={(a, r) => setPopover({ a, rect: r })}
          />
          <AssignmentList
            rows={kid.upcoming}
            label="Upcoming · next 14 days"
            tone="blue"
            selection={selection}
            onOpenAudit={setAudit}
            onOpenPopover={(a, r) => setPopover({ a, rect: r })}
          />

          <GradeTrendsMini trends={kid.grade_trends} />
        </section>
      ))}

      {data.messages_last_7d.length > 0 && (
        <section className="surface mb-6 overflow-hidden">
          <header className="px-4 py-3 border-b border-[color:var(--line)]">
            <h3 className="text-sm font-semibold">School messages · last 7 days · {data.messages_last_7d.length}</h3>
          </header>
          <ul>
            {data.messages_last_7d.slice(0, 15).map((m) => {
              const mm = m as unknown as {
                id: number; title: string | null; subject: string | null;
                title_en?: string | null; due_or_date: string | null;
                attachments?: import("../api").AttachmentLink[];
              };
              return (
                <li key={mm.id} className="px-4 py-2 border-t border-[color:var(--line-soft)] text-sm">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-medium">{mm.title || mm.subject}</span>
                    <span className="text-xs text-gray-500 whitespace-nowrap">{mm.due_or_date}</span>
                  </div>
                  {mm.title_en && mm.title_en !== (mm.title || mm.subject) && (
                    <div className="text-xs text-gray-600 italic">→ {mm.title_en}</div>
                  )}
                  {mm.attachments && mm.attachments.length > 0 && (
                    <Attachments items={mm.attachments} />
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <BulkActionBar
        selectedIds={selection.list}
        onClear={selection.clear}
        scope="Today"
      />
      {popover && (
        <StatusPopover a={popover.a} anchorRect={popover.rect}
          onClose={() => setPopover(null)} onSaved={refresh} />
      )}
      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
    </div>
  );
}
