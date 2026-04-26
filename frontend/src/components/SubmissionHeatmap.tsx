/**
 * SubmissionHeatmap — GitHub-style daily activity grid.
 *
 * 14 weeks × 7 days = 98 cells. Each cell is one day; cell color tints
 * by `closed / due` ratio for assignments due that day:
 *   no due       → muted gray (cell rendered but neutral)
 *   ratio == 0   → red (everything still open)
 *   0 < r < 1    → amber gradient
 *   ratio == 1   → green (all closed)
 *
 * Layout follows GitHub: weeks are columns, weekdays are rows. The most
 * recent week sits on the right; this is the convention parents are most
 * familiar with from the GitHub contribution graph.
 *
 * Hover: native HTML title showing date + due / closed counts.
 */
import { useQuery } from "@tanstack/react-query";

type Day = { date: string; due: number; closed: number; ratio: number };

const CELL = 11;
const GAP = 2;

function tone(d: Day): string {
  if (d.due === 0) return "var(--bg-muted)";
  // Ratio = 0 → red (all open); ratio = 1 → green; in between → amber gradient.
  if (d.ratio === 0) return "oklch(70% 0.18 25 / 0.85)";
  if (d.ratio === 1) return "oklch(70% 0.13 150 / 0.85)";
  // Lerp amber by ratio: less closed = stronger amber.
  const l = 70 + (1 - d.ratio) * 0;
  const c = 0.14 - (1 - d.ratio) * 0.02;
  return `oklch(${l}% ${c} 60 / ${0.55 + d.ratio * 0.3})`;
}

function dayOfWeek(iso: string): number {
  // Monday=0..Sunday=6 (matches Veracross schedule + UK convention).
  const d = new Date(iso + "T00:00:00Z");
  return (d.getUTCDay() + 6) % 7;
}

function formatTitle(d: Day): string {
  const date = d.date;
  if (d.due === 0) return `${date}: nothing due`;
  return `${date}: ${d.closed}/${d.due} closed`;
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
  const totalClosed = data.reduce((s, d) => s + d.closed, 0);
  const overallRatio = totalDue > 0 ? totalClosed / totalDue : 0;

  return (
    <div className={className}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs text-gray-500">
          Last {weeks} weeks · {totalClosed}/{totalDue} closed
          {totalDue > 0 && ` (${Math.round(overallRatio * 100)}%)`}
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
          <span>open</span>
          <span style={{ width: CELL, height: CELL, background: "oklch(70% 0.18 25 / 0.85)", borderRadius: 2 }} />
          <span style={{ width: CELL, height: CELL, background: "oklch(70% 0.12 60 / 0.7)", borderRadius: 2 }} />
          <span style={{ width: CELL, height: CELL, background: "oklch(70% 0.13 150 / 0.85)", borderRadius: 2 }} />
          <span>done</span>
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
