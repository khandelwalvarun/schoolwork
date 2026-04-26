import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, arrayMove } from "@dnd-kit/sortable";
import { api, Assignment, GradeTrend, SyllabusCycle, ChildBlock } from "../api";
import AuditDrawer from "../components/AuditDrawer";
import StatusPopover from "../components/StatusPopover";
import BulkActionBar from "../components/BulkActionBar";
import Attachments from "../components/Attachments";
import { AssignmentList } from "../components/AssignmentList";
import { useSelection } from "../components/useSelection";
import { useUiPrefs } from "../components/useUiPrefs";
import { SkeletonHero, SkeletonKidBlock } from "../components/Skeleton";
import { Button } from "../components/Button";
import { Sparkline } from "../components/Sparkline";
import { formatDate, formatRelative } from "../util/dates";

const BUCKET_DEFS: Record<string, { key: keyof ChildBlock; label: string; tone: "red" | "amber" | "blue" }> = {
  overdue:   { key: "overdue",   label: "Overdue",    tone: "red"   },
  due_today: { key: "due_today", label: "Due today",  tone: "amber" },
  upcoming:  { key: "upcoming",  label: "Upcoming · next 14 days", tone: "blue" },
};
const DEFAULT_BUCKET_ORDER = ["overdue", "due_today", "upcoming"];

function HeroBand({
  totals,
  lastSync,
  onSync,
  onSendDigest,
}: {
  totals: { overdue: number; due_today: number; upcoming: number };
  lastSync: {
    status: string | null;
    ended_at: string | null;
  } | null;
  onSync: () => void;
  onSendDigest: () => void;
}) {
  const ok = lastSync?.status === "ok";
  const never = !lastSync?.ended_at;
  const chipCls =
    never ? "chip-gray"
  : ok ? "chip-green"
  : "chip-red";
  return (
    <section className="mb-6">
      <div className="flex items-end justify-between mb-3">
        <div>
          <h2 className="text-2xl font-bold">Today</h2>
          <div className="mt-1 flex items-center gap-2 text-xs">
            <span className={chipCls}>
              {never ? "Never synced" : ok ? "✓ Synced" : "✗ Sync failed"}
            </span>
            {lastSync?.ended_at && (
              <span className="text-gray-500" title={lastSync.ended_at}>
                {formatRelative(lastSync.ended_at)}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {/* Things 3 rule: one primary action per page. Sync is the day-to-day,
              Send digest is a less frequent admin action. */}
          <Button variant="primary" size="sm" onClick={onSync}>Sync now</Button>
          <Button variant="secondary" size="sm" onClick={onSendDigest}>Send digest</Button>
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
      <Sparkline bars={sparkline} tone="red" width={84} height={18}
                 title={`Overdue, last 14 days. Currently ${latest}.`} />
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
          const recentPts = (t.recent || [])
            .map((r) => r.grade_pct)
            .filter((p): p is number => typeof p === "number");
          return (
            <div key={t.subject} className="flex items-center gap-2 whitespace-nowrap">
              <span className="text-gray-700">{t.subject}</span>
              <Sparkline
                points={recentPts.length > 0 ? recentPts : undefined}
                bars={recentPts.length === 0 ? t.sparkline : undefined}
                tone="purple"
                width={56}
                height={14}
                title={`${t.subject}: ${recentPts.join(", ")}%`}
              />
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

function KidSection({
  kid,
  selection,
  onOpenAudit,
  onOpenPopover,
  prefs,
}: {
  kid: ChildBlock;
  selection: ReturnType<typeof useSelection>;
  onOpenAudit: (a: Assignment) => void;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
  prefs: ReturnType<typeof useUiPrefs>;
}) {
  const order = prefs.bucketOrderFor(kid.child.id, DEFAULT_BUCKET_ORDER);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const ids = order.map((k) => `bucket-${kid.child.id}-${k}`);

  const onEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const fromIdx = ids.indexOf(String(e.active.id));
    const toIdx = ids.indexOf(String(e.over.id));
    if (fromIdx < 0 || toIdx < 0) return;
    const nextOrder = arrayMove(order, fromIdx, toIdx);
    prefs.setBucketOrder(kid.child.id, nextOrder);
  };

  return (
    <section className="surface mb-6 overflow-hidden">
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
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {order.map((bk) => {
            const def = BUCKET_DEFS[bk];
            if (!def) return null;
            const rows = (kid as unknown as Record<string, Assignment[]>)[def.key] ?? [];
            const bucketId = `bucket-${kid.child.id}-${bk}`;
            const collapsed = prefs.isCollapsed(bucketId, true);
            return (
              <AssignmentList
                key={bucketId}
                rows={rows}
                label={def.label}
                tone={def.tone}
                selection={selection}
                onOpenAudit={onOpenAudit}
                onOpenPopover={onOpenPopover}
                bucketId={bucketId}
                collapsed={collapsed}
                onToggleCollapsed={() => prefs.toggleCollapsed(bucketId)}
                sortableId={bucketId}
              />
            );
          })}
        </SortableContext>
      </DndContext>
      <GradeTrendsMini trends={kid.grade_trends} />
    </section>
  );
}

export default function Today() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["today"], queryFn: api.today });
  const selection = useSelection();
  const prefs = useUiPrefs();
  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [audit, setAudit] = useState<Assignment | null>(null);

  if (isLoading || !prefs.loaded) {
    return (
      <div>
        <SkeletonHero />
        <SkeletonKidBlock />
        <SkeletonKidBlock />
      </div>
    );
  }
  if (error) return <div className="text-red-700">Error: {String(error)}</div>;
  if (!data) return null;

  const refresh = () => qc.invalidateQueries({ queryKey: ["today"] });
  const sync = async () => { await api.syncNow(); setTimeout(refresh, 500); };
  const sendDigest = async () => { await api.digestRun(); };

  return (
    <div>
      <HeroBand
        totals={data.totals}
        lastSync={data.last_sync}
        onSync={sync}
        onSendDigest={sendDigest}
      />

      {data.children.map((kid) => (
        <KidSection
          key={kid.child.id}
          kid={kid}
          selection={selection}
          onOpenAudit={setAudit}
          onOpenPopover={(a, r) => setPopover({ a, rect: r })}
          prefs={prefs}
        />
      ))}

      {data.messages_last_7d.length > 0 && (
        <MessagesSection data={data.messages_last_7d} prefs={prefs} />
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

function MessagesSection({
  data,
  prefs,
}: {
  data: Array<{
    id: number; title: string | null; subject: string | null;
    title_en?: string | null; due_or_date: string | null;
    attachments?: import("../api").AttachmentLink[];
  }>;
  prefs: ReturnType<typeof useUiPrefs>;
}) {
  const bucketId = "section-messages-today";
  const collapsed = prefs.isCollapsed(bucketId, true);
  return (
    <section className="surface mb-6 overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        onClick={() => prefs.toggleCollapsed(bucketId)}
        className="w-full flex items-center gap-3 px-4 py-3 border-b border-[color:var(--line)] cursor-pointer hover:bg-[color:var(--bg-muted)] select-none"
      >
        <span className={"inline-block text-gray-400 transition-transform " + (collapsed ? "" : "rotate-90")} style={{ width: 10 }}>▶</span>
        <h3 className="text-sm font-semibold">
          School messages · last 7 days · {data.length}
        </h3>
      </div>
      {!collapsed && (
        <ul>
          {data.slice(0, 15).map((mm) => (
            <li key={mm.id} className="px-4 py-2 border-t border-[color:var(--line-soft)] text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium">{mm.title || mm.subject}</span>
                <span className="text-xs text-gray-500 whitespace-nowrap" title={mm.due_or_date ?? ""}>
                  {formatDate(mm.due_or_date)}
                </span>
              </div>
              {mm.title_en && mm.title_en !== (mm.title || mm.subject) && (
                <div className="text-xs text-gray-600 italic">→ {mm.title_en}</div>
              )}
              {mm.attachments && mm.attachments.length > 0 && (
                <Attachments items={mm.attachments} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
