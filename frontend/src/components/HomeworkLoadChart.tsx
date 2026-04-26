/**
 * HomeworkLoadChart — per-week assignment-load bars with the CBSE
 * policy cap drawn as a faint reference horizon.
 *
 * What we *can* show: how many assignments came due each ISO week,
 * multiplied by a per-class default minutes-per-item, → est_minutes.
 *
 * What we *can't* show: actual time-on-task. The school doesn't capture
 * it and we don't run a kid-side timer. So this is a load-estimator,
 * not a measurement — every bar's tooltip says so, and a `honest_caveat`
 * footer surfaces the same disclaimer in plain English.
 *
 * The CBSE Circular 52/2020 cap is rendered as a dashed horizontal line:
 *
 *   Class I–II    no homework                → cap = 0  (line at floor)
 *   Class III–V   ≤ 2 hr/week                → cap = 120
 *   Class VI–VIII ≤ 1 hr/day ≈ 6 hr/week     → cap = 360
 *   Class IX+     school discretion          → no line
 *
 * Bars over the cap tint amber; under tint blue. The honest framing —
 * "policy, not verdict" — is critical because the school does deviate
 * from CBSE policy in practice, and the chart is a reference, not a
 * scolding device.
 */
import { useQuery } from "@tanstack/react-query";
import { api, HomeworkLoadKid, HomeworkLoadWeek } from "../api";

const BAR_W = 28;
const BAR_GAP = 8;
const CHART_H = 96;
const TOP_PAD = 12;

const COLOR_OK     = "oklch(72% 0.10 235)";
const COLOR_OVER   = "oklch(70% 0.16 60)";
const COLOR_CAP    = "oklch(55% 0.13 25 / 0.55)";
const COLOR_AXIS   = "oklch(85% 0.01 250)";

function fmtWeekLabel(iso: string): string {
  // "2026-04-20" → "Apr 20"
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function tooltipFor(w: HomeworkLoadWeek, mpi: number): string {
  const date = new Date(w.week_start + "T00:00:00").toLocaleDateString(
    "en-US",
    { month: "long", day: "numeric", year: "numeric" },
  );
  const hours = (w.est_minutes / 60).toFixed(1);
  let src = "";
  if (w.by_source) {
    const parts: string[] = [];
    if (w.by_source.assigned)
      parts.push(`${w.by_source.assigned} by assigned-date`);
    if (w.by_source.due)
      parts.push(`${w.by_source.due} via due-date fallback`);
    if (parts.length) src = `\n${parts.join(" · ")}`;
  }
  return (
    `Week of ${date}\n` +
    `${w.items} assignment${w.items === 1 ? "" : "s"} given${src}\n` +
    `~${w.est_minutes} min (${hours} hr) at ${mpi} min/item — estimate, not measured`
  );
}

export function HomeworkLoadChart({
  childId,
  weeks = 8,
}: {
  childId: number;
  weeks?: number;
}) {
  const { data, isLoading } = useQuery<HomeworkLoadKid>({
    queryKey: ["homework-load", childId, weeks],
    queryFn: () => api.homeworkLoad(childId, weeks),
    staleTime: 60_000,
  });

  if (isLoading || !data) {
    return (
      <div className="surface p-4">
        <div className="h-section text-blue-700 mb-2">Homework load</div>
        <div className="h-24 skeleton rounded" />
      </div>
    );
  }

  const cap = data.cap_minutes;
  const peak = Math.max(
    ...data.weeks.map((w) => w.est_minutes),
    cap ?? 0,
    60,  // floor so an empty chart doesn't collapse to 0-height
  );
  // Round the y-domain up to a nice number for the axis label.
  const yMax = Math.ceil(peak / 60) * 60;

  const chartW = data.weeks.length * BAR_W + (data.weeks.length - 1) * BAR_GAP;
  const chartTotalH = CHART_H + TOP_PAD + 16;  // +16 for x-axis labels

  const yFor = (m: number) => TOP_PAD + (1 - m / yMax) * CHART_H;

  // Axis ticks: ~3 evenly spaced, labelled in hours.
  const ticks = [0, Math.round(yMax / 2 / 60) * 60, yMax];

  return (
    <div className="surface p-4">
      <div className="flex items-baseline justify-between mb-1">
        <span className="h-section text-blue-700">Homework load · by date assigned</span>
        <span className="text-xs text-gray-400">
          last {data.weeks.length} weeks · est. {data.est_minutes_per_item} min/item
        </span>
      </div>
      <div className="text-xs text-gray-500 mb-3">
        {data.cap_basis}
      </div>
      {data.fallback_share !== undefined && data.fallback_share > 0 && (
        <div
          className="text-[10px] text-amber-700 mb-2"
          title={data.bucketing_note}
        >
          {Math.round(data.fallback_share * 100)}% of items fell back to
          due-date (no assigned-date captured yet) — bucket placement
          may shift after the next heavy sync.
        </div>
      )}

      <div className="overflow-x-auto">
        <svg
          width={chartW + 40}
          height={chartTotalH}
          role="img"
          aria-label={`Estimated homework load over ${data.weeks.length} weeks`}
        >
          {/* y-axis ticks + faint grid */}
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={32}
                x2={32 + chartW}
                y1={yFor(t)}
                y2={yFor(t)}
                stroke={COLOR_AXIS}
                strokeWidth={1}
                strokeDasharray="2,3"
              />
              <text
                x={28}
                y={yFor(t) + 3}
                textAnchor="end"
                fontSize={9}
                fill="oklch(55% 0.01 250)"
              >
                {t === 0 ? "0" : `${(t / 60).toFixed(t % 60 === 0 ? 0 : 1)}h`}
              </text>
            </g>
          ))}

          {/* CBSE cap horizon — dashed, distinct color */}
          {cap !== null && cap > 0 && cap <= yMax && (
            <g>
              <line
                x1={32}
                x2={32 + chartW}
                y1={yFor(cap)}
                y2={yFor(cap)}
                stroke={COLOR_CAP}
                strokeWidth={1.5}
                strokeDasharray="4,3"
              />
              <text
                x={32 + chartW}
                y={yFor(cap) - 3}
                textAnchor="end"
                fontSize={9}
                fill={COLOR_CAP}
                fontWeight={600}
              >
                CBSE {(cap / 60).toFixed(cap % 60 === 0 ? 0 : 1)}h cap
              </text>
            </g>
          )}

          {/* bars */}
          {data.weeks.map((w, i) => {
            const x = 32 + i * (BAR_W + BAR_GAP);
            const yTop = yFor(w.est_minutes);
            const h = Math.max(0, CHART_H + TOP_PAD - yTop);
            const over = cap !== null && cap > 0 && w.est_minutes > cap;
            return (
              <g key={w.week_start}>
                <title>{tooltipFor(w, data.est_minutes_per_item)}</title>
                <rect
                  x={x}
                  y={yTop}
                  width={BAR_W}
                  height={h}
                  fill={over ? COLOR_OVER : COLOR_OK}
                  rx={2}
                />
                <text
                  x={x + BAR_W / 2}
                  y={CHART_H + TOP_PAD + 12}
                  textAnchor="middle"
                  fontSize={9}
                  fill="oklch(50% 0.01 250)"
                >
                  {fmtWeekLabel(w.week_start)}
                </text>
                {/* item count above the bar */}
                {w.items > 0 && (
                  <text
                    x={x + BAR_W / 2}
                    y={yTop - 3}
                    textAnchor="middle"
                    fontSize={9}
                    fill="oklch(40% 0.05 250)"
                    fontWeight={600}
                  >
                    {w.items}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <p className="text-[11px] text-gray-500 mt-2 leading-snug">
        {data.honest_caveat}
      </p>
    </div>
  );
}
