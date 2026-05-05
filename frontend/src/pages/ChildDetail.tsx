import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Assignment, GradeTrend } from "../api";
import { Button } from "../components/Button";
import AuditDrawer from "../components/AuditDrawer";
import ChildHeader from "../components/ChildHeader";
import { SkeletonKidBlock } from "../components/Skeleton";
import { Sparkline } from "../components/Sparkline";
import { SubmissionHeatmap } from "../components/SubmissionHeatmap";
import { HomeworkLoadChart } from "../components/HomeworkLoadChart";
import { PatternsCard } from "../components/PatternsCard";
import { SentimentTrendCard } from "../components/SentimentTrendCard";
import { PTMBriefPanel } from "../components/PTMBriefPanel";
import { SundayBriefPanel } from "../components/SundayBriefPanel";
import { WorthAChatTray } from "../components/WorthAChatTray";
import { FreshnessPelletStrip } from "../components/FreshnessPellet";
import { RecentClassworkCard } from "../components/RecentClassworkCard";
import { MindsparkPendingTray } from "../components/MindsparkPendingTray";
import { Tray, trayLineClass } from "../components/Tray";
import { CategoryChip } from "../components/StatusChips";
import { formatDate } from "../util/dates";
import { ExcellenceStatus } from "../api";

/** Up next preview — top 3 upcoming items for this kid. Renders as a
 *  Tray strip linking to /child/:id/assignments for the full sortable
 *  table. The bucket triplet (overdue/due-today/upcoming) used to
 *  duplicate Today here; this one preview answers "what's coming
 *  up?" without re-rendering the whole assignment grid. */
function UpNextPreview({
  childId,
  items,
  onOpenAudit,
  totalUpcoming,
}: {
  childId: number;
  items: Assignment[];
  onOpenAudit: (a: Assignment) => void;
  totalUpcoming: number;
}) {
  if (items.length === 0) return null;
  return (
    <Tray
      title="🗓 Up next"
      count={totalUpcoming}
      summary={totalUpcoming > items.length ? `showing first ${items.length}` : undefined}
      tone="blue"
      defaultCollapsed={false}
      rightSlot={
        <Link
          to={`/child/${childId}/assignments`}
          onClick={(e) => e.stopPropagation()}
          className="text-meta text-blue-700 hover:underline"
        >
          all assignments →
        </Link>
      }
    >
      <ul className="space-y-0.5">
        {items.map((a) => (
          <li key={a.id} className={trayLineClass("blue")}>
            <button
              type="button"
              onClick={() => onOpenAudit(a)}
              className="w-full flex items-baseline gap-2 text-left hover:bg-gray-50 rounded -mx-1 px-1"
            >
              <CategoryChip category={a.work_category as "homework" | "review" | "classwork" | null | undefined} />
              <span className="text-meta text-gray-500 w-20 truncate">{a.subject}</span>
              <span className="font-medium truncate min-w-0 flex-1">
                {a.title_en || a.title || "(untitled)"}
              </span>
              {a.due_or_date && (
                <span className="text-meta text-gray-500 whitespace-nowrap">
                  {formatDate(a.due_or_date)}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </Tray>
  );
}

/** One-line live summary inside the Analytics drawer's <summary>.
 *  Pulls signal from data already in the page so the user can see
 *  what's inside before opening — turning the drawer into a "drill
 *  down" rather than a "is anything in here?" mystery. */
function AnalyticsSummary({
  overdueTrend,
  overdueSparkline,
}: {
  overdueTrend: { count: number }[];
  overdueSparkline: string | null;
}) {
  if (!overdueTrend?.length) {
    return (
      <span className="text-xs text-gray-500">
        overdue trend · heatmap · load · patterns · sentiment
      </span>
    );
  }
  const now = overdueTrend[overdueTrend.length - 1]?.count ?? 0;
  const prev = overdueTrend[0]?.count ?? 0;
  const delta = now - prev;
  const trendCls =
    delta > 1
      ? "text-red-700"
      : delta < -1
      ? "text-emerald-700"
      : "text-gray-500";
  const arrow = delta > 1 ? "↑" : delta < -1 ? "↓" : "→";
  return (
    <span className="text-xs text-gray-500 inline-flex items-center gap-2">
      {overdueSparkline && (
        <Sparkline
          points={overdueTrend.map((p) => p.count)}
          tone="red"
          width={64}
          height={14}
          title="14-day overdue backlog"
        />
      )}
      <span className={trendCls}>
        backlog {arrow} {now}
        {delta !== 0 ? ` (${delta > 0 ? "+" : ""}${delta} in 14d)` : ""}
      </span>
      <span>· heatmap</span>
      <span>· load</span>
      <span>· patterns</span>
      <span>· sentiment</span>
    </span>
  );
}

export default function ChildDetail() {
  const { id } = useParams();
  const childId = Number(id);
  const [audit, setAudit] = useState<Assignment | null>(null);
  const [ptmOpen, setPtmOpen] = useState(false);
  const [sundayOpen, setSundayOpen] = useState(false);
  // Single bundled fetch — collapses what used to be five separate
  // queries (childDetail, excellence, classwork-count, anomalies-open,
  // worth-a-chat-count) into one round trip. The heavy chart endpoints
  // (heatmap, homework load, patterns, sentiment) stay independent —
  // they sit behind the collapsed Analytics drawer.
  const { data: bundle, isLoading, error } = useQuery({
    queryKey: ["child-full", childId],
    queryFn: () => api.childFull(childId),
    enabled: !isNaN(childId),
  });
  const data = bundle?.detail;
  const excellence: ExcellenceStatus | undefined = bundle?.excellence;
  if (isLoading) {
    return (
      <div>
        <ChildHeader title="" />
        <SkeletonKidBlock />
      </div>
    );
  }
  if (error) return <div className="text-red-700">Error: {String(error)}</div>;
  if (!data) return null;
  const c = data.child;
  return (
    <div>
      <ChildHeader title={c.display_name} />
      <div className="text-sm text-gray-500 mb-4 -mt-2 flex items-center gap-3 flex-wrap">
        Class {c.class_level}{c.class_section ? ` · ${c.class_section}` : ""}
        {data.syllabus_cycle && (
          <span className="chip-purple">
            {data.syllabus_cycle.name} · {data.syllabus_cycle.start} → {data.syllabus_cycle.end}
          </span>
        )}
        <FreshnessPelletStrip pellets={data.fresh_pellets} />
        {excellence && excellence.grades_count > 0 && (
          <span
            className={excellence.on_track ? "chip-green" : "chip-amber"}
            title={
              `Vasant Valley awards Excellence to students who maintain ≥ 85 % overall yearly avg ` +
              `for 5 consecutive years.\n` +
              `${excellence.year_label}: ${excellence.above_85_count}/${excellence.grades_count} grades ≥ 85 %, ` +
              `avg ${excellence.current_year_avg?.toFixed(1) ?? "—"} %.`
            }
          >
            {excellence.on_track ? "✓" : "⚠"} Excellence track ·{" "}
            {excellence.current_year_avg?.toFixed(1) ?? "—"} % avg ·{" "}
            {excellence.above_85_count}/{excellence.grades_count} ≥ 85 %
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {/* Two briefs sit at the top of the gestalt page. PTM is the
              primary action (one-per-page rule, Things 3); Sunday brief
              is secondary. Implementation uses the canonical Button
              primitive — same focus rings + sizing as everywhere else. */}
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setSundayOpen(true)}
            title="Open this kid's weekly Sunday brief (auto-refreshed nightly at 02:00 IST)"
          >
            Sunday brief
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={() => setPtmOpen(true)}
            title="Generate a Parent-Teacher Meeting prep brief (Claude, ~30s first time)"
          >
            PTM brief
          </Button>
        </div>
      </div>

      {/* Compact totals — links to the full views. ChildDetail is
          the GESTALT page (one-kid overview); the actionable buckets
          live on Today + /child/:id/assignments to avoid duplication. */}
      <section className="mb-6 flex items-baseline gap-5 text-body flex-wrap">
        {data.counts.overdue > 0 && (
          <Link to={`/child/${childId}/assignments?status=overdue`} className="hover:underline">
            <span className="font-semibold text-red-700 tabular-nums">{data.counts.overdue}</span>
            <span className="text-gray-500 ml-1">overdue</span>
          </Link>
        )}
        {data.counts.due_today > 0 && (
          <Link to={`/child/${childId}/assignments`} className="hover:underline">
            <span className="font-semibold text-amber-700 tabular-nums">{data.counts.due_today}</span>
            <span className="text-gray-500 ml-1">due today</span>
          </Link>
        )}
        <Link to={`/child/${childId}/assignments`} className="hover:underline">
          <span className="font-semibold text-blue-700 tabular-nums">{data.counts.upcoming}</span>
          <span className="text-gray-500 ml-1">upcoming</span>
        </Link>
        <Link to={`/child/${childId}/comments`} className="hover:underline">
          <span className="font-semibold text-gray-700 tabular-nums">{data.counts.comments}</span>
          <span className="text-gray-500 ml-1">comments</span>
        </Link>
      </section>

      <WorthAChatTray childId={childId} onOpenAudit={setAudit} />

      <MindsparkPendingTray childId={childId} />

      <RecentClassworkCard childId={childId} days={30} />

      {/* Subjects — one tight row per subject, each clickable to the
          filtered grades view. This is the gestalt question the
          parent comes here to answer: "how is X doing in each
          subject right now?" */}
      {data.grade_trends.length > 0 && (
        <Tray
          title="📈 Subjects"
          count={data.grade_trends.length}
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
          <ul className="space-y-0.5">
            {data.grade_trends.map((t: GradeTrend) => {
              const recentPts = (t.recent || [])
                .map((r) => r.grade_pct)
                .filter((p): p is number => typeof p === "number");
              const arrowColor =
                t.arrow === "↑"
                  ? "text-emerald-700"
                  : t.arrow === "↓"
                  ? "text-red-700"
                  : "text-gray-500";
              return (
                <li key={t.subject} className={trayLineClass("purple")}>
                  <Link
                    to={`/child/${childId}/grades?subject=${encodeURIComponent(t.subject)}`}
                    className="flex items-center gap-3 hover:bg-gray-50 rounded -mx-1 px-1"
                  >
                    <span className="text-gray-700 w-40 truncate" title={t.subject}>
                      {t.subject}
                    </span>
                    <Sparkline
                      points={recentPts.length > 0 ? recentPts : undefined}
                      bars={recentPts.length === 0 ? t.sparkline : undefined}
                      tone="purple"
                      width={84}
                      height={16}
                      title={`${t.subject} grades: ${recentPts.join(", ")}%`}
                    />
                    <span className={arrowColor + " w-3 text-center"}>{t.arrow}</span>
                    <span className="font-medium text-gray-900 w-12 text-right tabular-nums">
                      {t.latest.toFixed(0)}%
                    </span>
                    <span className="text-meta text-gray-500 w-20">
                      avg {t.avg.toFixed(0)}% (n={t.count})
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Tray>
      )}

      {/* Up next — top 3 upcoming. Gestalt shows just enough to know
          what to expect; the full list is one click away. */}
      <UpNextPreview
        childId={childId}
        items={data.upcoming.slice(0, 3)}
        onOpenAudit={setAudit}
        totalUpcoming={data.counts.upcoming}
      />

      <details className="mb-6 group" open={false}>
        <summary className="cursor-pointer flex items-center gap-2 text-body select-none flex-wrap py-2 border-b border-[color:var(--line-soft)]">
          <span className="text-gray-400 transition-transform group-open:rotate-90 inline-block w-3" aria-hidden>▶</span>
          <span className="font-semibold text-gray-700">📊 Analytics</span>
          <AnalyticsSummary
            overdueTrend={data.overdue_trend}
            overdueSparkline={data.overdue_sparkline ?? null}
          />
        </summary>
        <div className="px-2 py-4 space-y-6">
          <div className="grid md:grid-cols-2 gap-6">
            {data.overdue_sparkline && (
              <div>
                <div className="h-section mb-1">14-day overdue backlog</div>
                <Sparkline
                  points={data.overdue_trend.map((p) => p.count)}
                  tone="red"
                  width={240}
                  height={32}
                  title={`Overdue last 14 days. Now ${data.overdue_trend[data.overdue_trend.length - 1]?.count}.`}
                />
                <div className="text-meta text-gray-500 mt-1">
                  {data.overdue_trend[0]?.date} → {data.overdue_trend[data.overdue_trend.length - 1]?.date}
                  &nbsp;· now {data.overdue_trend[data.overdue_trend.length - 1]?.count}
                </div>
              </div>
            )}
            <div>
              <div className="h-section mb-1">Submission pattern · 14 weeks</div>
              <SubmissionHeatmap childId={childId} weeks={14} />
            </div>
          </div>
          <HomeworkLoadChart childId={childId} weeks={8} />
          <PatternsCard childId={childId} />
          <SentimentTrendCard childId={childId} />
        </div>
      </details>

      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
      {ptmOpen && (
        <PTMBriefPanel childId={childId} onClose={() => setPtmOpen(false)} />
      )}
      {sundayOpen && (
        <SundayBriefPanel
          childId={childId}
          childName={c.display_name}
          onClose={() => setSundayOpen(false)}
        />
      )}
    </div>
  );
}
