/**
 * SubmissionHeatmap — GitHub-style daily activity grid.
 *
 * 14 weeks × 7 days = 98 cells. Each cell is one day. The cell tint maps
 * to the *dominant inferred state* of assignments due that day:
 *
 *   nothing due                                  → gray
 *   any likely_missing                            → red
 *   any pending (past due, still 'assigned')      → amber
 *   all graded or parent_marked                   → green
 *
 * "likely_missing" is the cockpit's honest answer to "did this kid hand
 * it in?" — the school doesn't mark 'submitted' reliably and the parent
 * might forget, so anything past-due + still 'assigned' for >7 days is
 * worth flagging; under that grace window we render amber ("pending")
 * not red ("missing").
 *
 * Layout follows GitHub: weeks are columns, weekdays are rows. The most
 * recent week sits on the right.
 *
 * Hover: native HTML title showing date + per-bucket counts.
 */
import { useQuery } from "@tanstack/react-query";

type Day = {
  date: string;
  due: number;
  graded: number;
  parent_marked: number;
  pending: number;
  likely_missing: number;
  closed: number;
  ratio: number;
};

const CELL = 11;
const GAP = 2;

const COLOR_GREEN = "oklch(70% 0.13 150 / 0.85)";
const COLOR_AMBER = "oklch(72% 0.14 60 / 0.85)";
const COLOR_RED = "oklch(70% 0.18 25 / 0.85)";

function tone(d: Day): string {
  if (d.due === 0) return "var(--bg-muted)";
  if (d.likely_missing > 0) return COLOR_RED;
  if (d.pending > 0) return COLOR_AMBER;
  return COLOR_GREEN;
}

function dayOfWeek(iso: string): number {
  // Monday=0..Sunday=6 (matches Veracross schedule + UK convention).
  const d = new Date(iso + "T00:00:00Z");
  return (d.getUTCDay() + 6) % 7;
}

function formatTitle(d: Day): string {
  if (d.due === 0) return `${d.date}: nothing due`;
  const parts: string[] = [];
  if (d.graded) parts.push(`${d.graded} graded`);
  if (d.parent_marked) parts.push(`${d.parent_marked} parent-marked`);
  if (d.pending) parts.push(`${d.pending} pending`);
  if (d.likely_missing) parts.push(`${d.likely_missing} likely missing`);
  return `${d.date} · due ${d.due} — ${parts.join(", ")}`;
}

export function SubmissionHeatmap({
  childId,
  weeks = 14,
  className = "",
}: {
  childId?: number;
  weeks?: number;
  className?: string;
}) {
  const { data } = useQuery<Day[]>({
    queryKey: ["submission-heatmap", childId, weeks],
    queryFn: () =>
      fetch(
        `/api/submission-heatmap?weeks=${weeks}${childId ? `&child_id=${childId}` : ""}`,
      ).then((r) => r.json()),
    staleTime: 60_000,
  });

  if (!data || data.length === 0) {
    return (
      <div
        aria-hidden
        className={"skeleton " + className}
        style={{ width: weeks * (CELL + GAP), height: 7 * (CELL + GAP) }}
      />
    );
  }

  // Bucket days into a column per week. Each column = the 7 weekday slots.
  // First column may have empty slots at the top (the oldest day might not
  // be a Monday); pad with null.
  const firstDow = dayOfWeek(data[0].date);
  const padded: (Day | null)[] = [...Array(firstDow).fill(null), ...data];
  const cols: (Day | null)[][] = [];
  for (let i = 0; i < padded.length; i += 7) {
    const slice = padded.slice(i, i + 7);
    while (slice.length < 7) slice.push(null);
    cols.push(slice);
  }

  const totalDue = data.reduce((s, d) => s + d.due, 0);
  const totalGraded = data.reduce((s, d) => s + d.graded, 0);
  const totalParent = data.reduce((s, d) => s + d.parent_marked, 0);
  const totalPending = data.reduce((s, d) => s + d.pending, 0);
  const totalMissing = data.reduce((s, d) => s + d.likely_missing, 0);

  return (
    <div className={className}>
      <div className="flex items-start justify-between mb-2 gap-3 flex-wrap">
        <div className="text-xs text-gray-500 leading-snug">
          <div>
            Last {weeks} weeks · {totalDue} due
            {totalGraded > 0 && ` · ${totalGraded} graded`}
            {totalParent > 0 && ` · ${totalParent} parent-marked`}
            {totalPending > 0 && ` · ${totalPending} pending`}
            {totalMissing > 0 && (
              <> · <span className="text-red-700 font-medium">{totalMissing} likely missing</span></>
            )}
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">
            "Pending" = past-due, still assigned (≤ 7 days). The school doesn't always mark
            submissions; if you know an item is in, mark it done so it stops counting as
            pending or missing.
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-gray-500 whitespace-nowrap">
          <span style={{ width: CELL, height: CELL, background: COLOR_GREEN, borderRadius: 2 }} title="graded or parent-marked" />
          <span>done</span>
          <span style={{ width: CELL, height: CELL, background: COLOR_AMBER, borderRadius: 2 }} title="past due, still assigned ≤ 7 d" />
          <span>pending</span>
          <span style={{ width: CELL, height: CELL, background: COLOR_RED, borderRadius: 2 }} title="past due > 7 d, no confirmation" />
          <span>missing</span>
        </div>
      </div>
      <div className="flex gap-[2px]" role="img" aria-label={`Submission heatmap, last ${weeks} weeks`}>
        {cols.map((col, ci) => (
          <div key={ci} className="flex flex-col gap-[2px]">
            {col.map((d, ri) =>
              d ? (
                <div
                  key={ri}
                  title={formatTitle(d)}
                  style={{
                    width: CELL,
                    height: CELL,
                    background: tone(d),
                    borderRadius: 2,
                  }}
                />
              ) : (
                <div
                  key={ri}
                  style={{ width: CELL, height: CELL, background: "transparent" }}
                />
              ),
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
