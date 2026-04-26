import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Assignment, GradeTrend } from "../api";
import AuditDrawer from "../components/AuditDrawer";
import StatusPopover from "../components/StatusPopover";
import ChildHeader from "../components/ChildHeader";
import BulkActionBar from "../components/BulkActionBar";
import { AssignmentList } from "../components/AssignmentList";
import { useSelection } from "../components/useSelection";
import { useUiPrefs } from "../components/useUiPrefs";
import { SkeletonKidBlock } from "../components/Skeleton";
import { Sparkline } from "../components/Sparkline";
import { SubmissionHeatmap } from "../components/SubmissionHeatmap";
import { HomeworkLoadChart } from "../components/HomeworkLoadChart";
import { PatternsCard } from "../components/PatternsCard";
import { SentimentTrendCard } from "../components/SentimentTrendCard";
import { PTMBriefPanel } from "../components/PTMBriefPanel";
import { SundayBriefPanel } from "../components/SundayBriefPanel";
import { ExcellenceStatus } from "../api";

export default function ChildDetail() {
  const { id } = useParams();
  const childId = Number(id);
  const [audit, setAudit] = useState<Assignment | null>(null);
  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [ptmOpen, setPtmOpen] = useState(false);
  const [sundayOpen, setSundayOpen] = useState(false);
  const selection = useSelection();
  const prefs = useUiPrefs();
  const { data, isLoading, error } = useQuery({
    queryKey: ["child-detail", childId],
    queryFn: () => api.childDetail(childId),
    enabled: !isNaN(childId),
  });
  const { data: excellence } = useQuery<ExcellenceStatus>({
    queryKey: ["excellence", childId],
    queryFn: () => api.excellence(childId),
    enabled: !isNaN(childId),
  });
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
          <button
            type="button"
            onClick={() => setSundayOpen(true)}
            className="text-xs px-2 py-1 border border-purple-300 text-purple-800 bg-purple-50 hover:bg-purple-100 rounded"
            title="Open this kid's weekly Sunday brief (auto-refreshed nightly at 02:00 IST)"
          >
            📋 Sunday brief
          </button>
          <button
            type="button"
            onClick={() => setPtmOpen(true)}
            className="text-xs px-2 py-1 border border-purple-300 text-purple-800 bg-purple-50 hover:bg-purple-100 rounded"
            title="Generate a Parent-Teacher Meeting prep brief (Claude, ~30s first time)"
          >
            🗒 PTM brief
          </button>
        </div>
      </div>

      <section className="surface mb-6 p-5 flex items-center gap-10">
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Overdue</div>
          <div className="text-3xl font-bold text-red-700">{data.counts.overdue}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Due today</div>
          <div className="text-3xl font-bold text-amber-700">{data.counts.due_today}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Upcoming</div>
          <div className="text-3xl font-bold text-blue-700">{data.counts.upcoming}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500">Comments</div>
          <div className="text-3xl font-bold text-gray-700">{data.counts.comments}</div>
        </div>
      </section>

      <div className="surface mb-6 p-4 grid md:grid-cols-2 gap-6">
        {data.overdue_sparkline && (
          <div>
            <div className="text-xs uppercase tracking-wider text-gray-500 mb-1">14-day overdue backlog</div>
            <Sparkline
              points={data.overdue_trend.map((p) => p.count)}
              tone="red"
              width={240}
              height={32}
              title={`Overdue last 14 days. Now ${data.overdue_trend[data.overdue_trend.length - 1]?.count}.`}
            />
            <div className="text-xs text-gray-500 mt-1">
              {data.overdue_trend[0]?.date} → {data.overdue_trend[data.overdue_trend.length - 1]?.date}
              &nbsp;· now {data.overdue_trend[data.overdue_trend.length - 1]?.count}
            </div>
          </div>
        )}
        <div>
          <div className="text-xs uppercase tracking-wider text-gray-500 mb-1">Submission pattern · 14 weeks</div>
          <SubmissionHeatmap childId={childId} weeks={14} />
        </div>
      </div>

      <div className="mb-6">
        <HomeworkLoadChart childId={childId} weeks={8} />
      </div>

      <div className="mb-6">
        <PatternsCard childId={childId} />
      </div>

      <div className="mb-6">
        <SentimentTrendCard childId={childId} />
      </div>

      <section className="surface mb-6 overflow-hidden">
        {(["overdue", "due_today", "upcoming"] as const).map((bk) => {
          const meta: Record<string, { label: string; tone: "red" | "amber" | "blue" }> = {
            overdue:   { label: "Overdue",    tone: "red"   },
            due_today: { label: "Due today",  tone: "amber" },
            upcoming:  { label: "Upcoming",   tone: "blue"  },
          };
          const rows = (data as unknown as Record<string, Assignment[]>)[bk] ?? [];
          const bucketId = `bucket-${childId}-${bk}-detail`;
          const collapsed = prefs.isCollapsed(bucketId, true);
          return (
            <AssignmentList
              key={bk}
              rows={rows}
              label={meta[bk].label}
              tone={meta[bk].tone}
              selection={selection}
              onOpenAudit={setAudit}
              onOpenPopover={(a, r) => setPopover({ a, rect: r })}
              bucketId={bucketId}
              collapsed={collapsed}
              onToggleCollapsed={() => prefs.toggleCollapsed(bucketId)}
            />
          );
        })}
      </section>

      {data.grade_trends.length > 0 && (
        <section className="surface mb-6 p-4">
          <h3 className="h-section text-purple-700 mb-3">Grade trends</h3>
          <table className="w-full text-sm"><tbody>
            {data.grade_trends.map((t: GradeTrend) => {
              const recentPts = (t.recent || [])
                .map((r) => r.grade_pct)
                .filter((p): p is number => typeof p === "number");
              return (
              <tr key={t.subject} className="border-t border-[color:var(--line-soft)]">
                <td className="py-1">{t.subject}</td>
                <td className="py-1">
                  <Sparkline
                    points={recentPts.length > 0 ? recentPts : undefined}
                    bars={recentPts.length === 0 ? t.sparkline : undefined}
                    tone="purple"
                    width={84}
                    height={18}
                    title={`${t.subject} grades: ${recentPts.join(", ")}%`}
                  />
                </td>
                <td className="py-1 text-lg">{t.arrow}</td>
                <td className="py-1">latest <b>{t.latest.toFixed(0)}%</b></td>
                <td className="py-1 text-gray-500">avg {t.avg.toFixed(0)}% (n={t.count})</td>
              </tr>
            );
            })}
          </tbody></table>
          <div className="mt-2 text-xs">
            <Link className="text-blue-700 hover:underline" to={`/child/${childId}/grades`}>See full grades →</Link>
          </div>
        </section>
      )}

      <BulkActionBar
        selectedIds={selection.list}
        onClear={selection.clear}
        scope={c.display_name}
      />
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
      {popover && (
        <StatusPopover a={popover.a} anchorRect={popover.rect}
          onClose={() => setPopover(null)} />
      )}
    </div>
  );
}
