/**
 * SentimentTrendCard — quiet trend across the rolling window of teacher
 * comments. Per the plan: never alert on a single comment, surface only
 * the *direction* of the trend (rising / falling / flat). Renders as a
 * small sparkline with the most-recent bucket dotted, plus a one-word
 * direction chip.
 *
 * Empty / sparse data renders an explicit "no comments yet in the
 * window" line — better than a misleading flat line at zero. Buckets
 * with no activity are gaps in the sparkline (skipped, not zero-filled).
 */
import { useQuery } from "@tanstack/react-query";
import { api, SentimentPoint, SentimentTrend } from "../api";

const TONE_BG = {
  rising: "border-green-300 text-green-800 bg-green-50",
  falling: "border-red-300 text-red-800 bg-red-50",
  flat: "border-gray-300 text-gray-700 bg-gray-50",
} as const;

function fmtBucket(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function MiniSparkline({ points }: { points: SentimentPoint[] }) {
  // Map mean_score [-1, +1] → y in [12, 0]; null = gap.
  const W = 120;
  const H = 16;
  const pad = 1;
  const usable = H - 2 * pad;
  if (points.length === 0) return null;
  const stepX = points.length > 1 ? W / (points.length - 1) : W;

  const segments: Array<Array<[number, number]>> = [];
  let cur: Array<[number, number]> = [];
  points.forEach((p, i) => {
    if (p.mean_score === null) {
      if (cur.length > 0) {
        segments.push(cur);
        cur = [];
      }
      return;
    }
    const x = i * stepX;
    const y = H - pad - ((p.mean_score + 1) / 2) * usable;
    cur.push([x, y]);
  });
  if (cur.length > 0) segments.push(cur);

  const baseY = H - pad - 0.5 * usable;  // 0-line for sentiment
  const lastNonNull = [...points].reverse().find((p) => p.mean_score !== null);
  const lastIdx = lastNonNull ? points.lastIndexOf(lastNonNull) : -1;
  const lastX = lastIdx >= 0 ? lastIdx * stepX : 0;
  const lastY =
    lastIdx >= 0 && lastNonNull && lastNonNull.mean_score !== null
      ? H - pad - ((lastNonNull.mean_score + 1) / 2) * usable
      : 0;

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Sentiment trend"
    >
      <line
        x1={0}
        y1={baseY}
        x2={W}
        y2={baseY}
        stroke="oklch(80% 0.005 250)"
        strokeWidth={1}
        strokeDasharray="2,3"
      />
      {segments.map((seg, idx) => {
        const path = seg
          .map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`))
          .join(" ");
        return (
          <path
            key={idx}
            d={path}
            fill="none"
            stroke="oklch(40% 0.10 235)"
            strokeWidth={1.4}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        );
      })}
      {lastIdx >= 0 && (
        <circle cx={lastX} cy={lastY} r={2.2} fill="oklch(40% 0.10 235)" />
      )}
    </svg>
  );
}

export function SentimentTrendCard({ childId }: { childId: number }) {
  const { data, isLoading } = useQuery<SentimentTrend>({
    queryKey: ["sentiment-trend", childId],
    queryFn: () => api.sentimentTrend(childId),
    staleTime: 60_000,
  });

  if (isLoading || !data) {
    return (
      <div className="surface p-4">
        <div className="h-section text-blue-700 mb-2">Comment sentiment</div>
        <div className="h-10 skeleton rounded" />
      </div>
    );
  }

  if (data.total_comments === 0) {
    return (
      <div className="surface p-4">
        <div className="flex items-baseline justify-between mb-1">
          <span className="h-section text-blue-700">Comment sentiment</span>
          <span className="text-xs text-gray-400">last {data.window_days} days</span>
        </div>
        <div className="text-sm text-gray-500 italic">
          No teacher comments in the window. We'll start drawing the trend
          once a few land.
        </div>
      </div>
    );
  }

  const directionLabel =
    data.direction === "rising"
      ? "Trend rising"
      : data.direction === "falling"
        ? "Trend falling"
        : data.direction === "flat"
          ? "Trend flat"
          : "Mixed";

  return (
    <div className="surface p-4">
      <div className="flex items-baseline justify-between mb-2">
        <span className="h-section text-blue-700">Comment sentiment</span>
        <span className="text-xs text-gray-400">
          {data.total_comments} comment{data.total_comments === 1 ? "" : "s"} ·
          last {data.window_days} d
        </span>
      </div>
      <div className="flex items-center gap-3">
        <MiniSparkline points={data.points} />
        {data.direction && (
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${
              TONE_BG[data.direction]
            }`}
          >
            {directionLabel.toLowerCase()}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 mt-2 text-[10px] text-gray-400">
        {data.points.map((p) => (
          <span key={p.bucket_start} className="w-[28px] text-center">
            {fmtBucket(p.bucket_start)}
          </span>
        ))}
      </div>
      <p className="text-[11px] text-gray-500 mt-2 leading-snug">
        {data.honest_caveat}
      </p>
    </div>
  );
}
