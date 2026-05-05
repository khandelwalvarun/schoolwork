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
import { ShakyTopicsTray } from "../components/ShakyTopicsTray";
import { DailyBriefCard } from "../components/DailyBriefCard";
import { FreshnessPelletStrip } from "../components/FreshnessPellet";
import { AnomalyTray } from "../components/AnomalyTray";
import { Tray } from "../components/Tray";
import { ClassworkTodayStrip } from "../components/ClassworkTodayStrip";
import { MindsparkPendingTray } from "../components/MindsparkPendingTray";
import { formatDate } from "../util/dates";

// Bucket labels — sentence case + short. The bucket header has the
// tone colour, count, and chevron; the label only needs to name the
// bucket. Earlier `Upcoming · next 14 days` made the header heavy
// once the count was appended (`UPCOMING · NEXT 14 DAYS · 4`).
const BUCKET_DEFS: Record<string, { key: keyof ChildBlock; label: string; tone: "red" | "amber" | "blue" }> = {
  overdue:   { key: "overdue",   label: "Overdue",    tone: "red"   },
  due_today: { key: "due_today", label: "Due today",  tone: "amber" },
  upcoming:  { key: "upcoming",  label: "Upcoming",   tone: "blue"  },
};
const DEFAULT_BUCKET_ORDER = ["overdue", "due_today", "upcoming"];

function HeroBand({
  totals,
  onSync,
  onSendDigest,
}: {
  totals: { overdue: number; due_today: number; upcoming: number };
  onSync: () => void;
  onSendDigest: () => void;
}) {
  return (
    <section className="mb-6">
      {/* The global SyncStatusBar (mounted in App.tsx) already shows
          the synced/last-sync state at the very top of every page —
          the in-page chip was a duplicate. Removed for calm. */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 sm:gap-0 mb-3">
        <h2 className="text-xl sm:text-2xl font-bold">Today</h2>
        <div className="flex gap-2">
          {/* Both demoted to ghost — Today's primary action is
              READING the trays, not running a sync. The global
              SyncStatusBar already shows "✓ Synced 23 min ago"; the
              user only clicks ↻ when something feels stale. */}
          <Button
            variant="ghost"
            size="sm"
            onClick={onSync}
            title="Sync now (also runs hourly automatically)"
          >
            ↻ Sync
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onSendDigest}
            title="Send the digest email"
          >
            Send digest
          </Button>
        </div>
      </div>
      {/* Totals strip — only shown when there's something to look
          at. When overdue + due-today are both 0, the absence of the
          red/amber tray strips below already communicates "nothing
          urgent"; repeating it here as zeros adds noise without
          information. The "upcoming · 14 days" count alone isn't
          actionable enough to justify keeping the strip alive. */}
      {(totals.overdue > 0 || totals.due_today > 0) && (
        <div className="flex items-baseline gap-x-5 gap-y-1 text-body flex-wrap">
          <span className="text-gray-500 hidden sm:inline">Across both kids:</span>
          {totals.overdue > 0 && (
            <span>
              <span className="font-semibold text-red-700 tabular-nums">{totals.overdue}</span>
              <span className="text-gray-500 ml-1">overdue</span>
            </span>
          )}
          {totals.due_today > 0 && (
            <span>
              <span className="font-semibold text-amber-700 tabular-nums">{totals.due_today}</span>
              <span className="text-gray-500 ml-1">due today</span>
            </span>
          )}
          {totals.upcoming > 0 && (
            <span>
              <span className="font-semibold text-blue-700 tabular-nums">{totals.upcoming}</span>
              <span className="text-gray-500 ml-1">upcoming · 14 days</span>
            </span>
          )}
        </div>
      )}
    </section>
  );
}

function KidBacklog({ sparkline, latest }: { sparkline: string; latest: number }) {
  if (!sparkline) return null;
  // Number-first layout: the count is the answer to "how big is the
  // backlog right now?", so it gets the prominent position. The
  // sparkline + label are context. Earlier order (`14-day backlog ▁▂▃ now 36`)
  // buried the most useful number at the end.
  return (
    <div className="text-meta text-gray-600 flex items-center gap-2">
      <span>
        <span className={"font-semibold tabular-nums " + (latest > 0 ? "text-red-700" : "text-gray-700")}>
          {latest}
        </span>
        <span className="text-gray-500"> overdue</span>
      </span>
      <Sparkline bars={sparkline} tone="red" width={84} height={14}
                 title={`Overdue, last 14 days. Currently ${latest}.`} />
      <span className="text-gray-500">14d</span>
    </div>
  );
}

function GradeTrendsMini({ trends, childId }: { trends: GradeTrend[]; childId: number }) {
  if (!trends || trends.length === 0) return null;
  // Compute a one-line summary for the collapsed Tray header — most
  // recent direction across subjects (so the parent sees a hint
  // without expanding).
  const ups = trends.filter((t) => t.arrow === "↑").length;
  const downs = trends.filter((t) => t.arrow === "↓").length;
  const summary =
    downs > 0
      ? `${downs} down · ${ups} up · ${trends.length - downs - ups} flat`
      : ups > 0
      ? `${ups} up · ${trends.length - ups} flat`
      : "all flat";
  return (
    <Tray
      title="📈 Grade trend"
      count={trends.length}
      summary={summary}
      tone="purple"
      defaultCollapsed={false}
      rightSlot={
        <Link
          to={`/child/${childId}/grades`}
          onClick={(e) => e.stopPropagation()}
          className="text-meta text-purple-700 hover:underline"
        >
          all grades →
        </Link>
      }
    >
      {/* Subject-per-line grid (Tufte: small multiples, one tight row
          per subject). On narrow screens it stays single-column; on
          wide it goes 2-up. Previous flex-wrap rendered subjects +
          sparklines + arrows in an unscannable run-on. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-0.5 text-body pl-2">
        {trends.map((t) => {
          const arrowColor =
            t.arrow === "↑" ? "text-emerald-700"
          : t.arrow === "↓" ? "text-red-700"
          : "text-gray-500";
          const recentPts = (t.recent || [])
            .map((r) => r.grade_pct)
            .filter((p): p is number => typeof p === "number");
          return (
            <Link
              key={t.subject}
              to={`/child/${childId}/grades?subject=${encodeURIComponent(t.subject)}`}
              className="flex items-center gap-2 hover:bg-gray-50 rounded px-1 -mx-1"
              title={`Open ${t.subject} grades`}
            >
              <span className="text-gray-700 w-32 truncate" title={t.subject}>
                {t.subject}
              </span>
              <Sparkline
                points={recentPts.length > 0 ? recentPts : undefined}
                bars={recentPts.length === 0 ? t.sparkline : undefined}
                tone="purple"
                width={64}
                height={14}
                title={`${t.subject}: ${recentPts.join(", ")}%`}
              />
              <span className={arrowColor + " w-3 text-center"}>{t.arrow}</span>
              <span className="text-gray-700 font-medium w-10 text-right tabular-nums">
                {t.latest.toFixed(0)}%
              </span>
              <span className="text-meta text-gray-500">(n={t.count})</span>
            </Link>
          );
        })}
      </div>
    </Tray>
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

// ClassworkChip — removed from the kid header. The ClassworkTodayStrip
// (rendered immediately below the header) already surfaces classwork
// status with the same C-badge and a link to /child/:id#classwork, so
// the chip was visual duplication that forced the pellet row to wrap.
// Component intentionally deleted; if you re-add a fortnightly count
// somewhere later, prefer compact inline text in ClassworkTodayStrip.

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

  // Kid block: card chrome (border + shadow + rounded) removed.
  // Top border + larger top spacing now demarcate one kid from the
  // next, matching the lighter "tray strip" vocabulary above. The
  // eye reads the page as a sequence of strips, not nested cards
  // within cards.
  return (
    <section className="mb-8 pt-5 border-t border-[color:var(--line)]">
      {/* Mobile-friendly stacking: on narrow viewports the header
          collapses into two rows (name + chips, then nav). The
          backlog sparkline is hidden on mobile (it's a glanceable
          luxury, not actionable). Touch targets bumped to 32px min. */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3 mb-2">
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap min-w-0">
          <Link
            to={`/child/${kid.child.id}`}
            className="text-base sm:text-lg font-semibold hover:text-blue-700 truncate min-h-[32px] inline-flex items-center"
          >
            {kid.child.display_name}
          </Link>
          <span className="text-xs sm:text-sm text-gray-500 whitespace-nowrap">· {kid.child.class_section}</span>
          <CycleBadge cycle={kid.syllabus_cycle} />
          <FreshnessPelletStrip pellets={kid.fresh_pellets} />
          {/* ClassworkChip removed from the header: the
              ClassworkTodayStrip immediately below already shows
              "In class · today · N · subjects" + a link to all
              classwork. The chip duplicated that information and
              forced the pellet row to wrap. */}
        </div>
        {/* Stack the nav above the backlog sparkline so neither
            truncates. Previous side-by-side layout cut "Syllabus" to
            "Sylla…" on tighter widths. */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <nav className="text-meta text-gray-600 flex gap-3 whitespace-nowrap">
            <Link to={`/child/${kid.child.id}/assignments`} className="hover:text-blue-700 py-0.5">All</Link>
            <Link to={`/child/${kid.child.id}/grades`} className="hover:text-blue-700 py-0.5">Grades</Link>
            <Link to={`/child/${kid.child.id}/syllabus`} className="hover:text-blue-700 py-0.5">Syllabus</Link>
          </nav>
          <div className="hidden sm:block">
            <KidBacklog sparkline={kid.overdue_sparkline}
              latest={kid.overdue_trend[kid.overdue_trend.length - 1]?.count ?? 0} />
          </div>
        </div>
      </header>
      <ClassworkTodayStrip childId={kid.child.id} />
      {/* Mindspark pending practice — surfaces weak / decaying
          topics as practice todos. Reads as another tray sibling so
          the parent sees "what's pending" as one concern, not split
          across school assignments and Mindspark practice. */}
      <MindsparkPendingTray childId={kid.child.id} />
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
      <GradeTrendsMini trends={kid.grade_trends} childId={kid.child.id} />
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
        onSync={sync}
        onSendDigest={sendDigest}
      />
      <DailyBriefCard />
      <AnomalyTray />
      <ShakyTopicsTray />

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
