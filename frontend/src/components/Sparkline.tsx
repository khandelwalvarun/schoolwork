/**
 * Sparkline — Tufte's "wordsize graphic", as inline SVG.
 *
 * Replaces the existing ASCII sparklines (▁▂▃▄▅▆▇█ via monospace
 * Unicode block chars). The Tufte spec: a low-aspect line + a single
 * colored end dot at the most recent value, optional reference baseline,
 * and a hover tooltip that lists the points. Goal: scannable in a row,
 * meaningful at a glance, never trying to be a full chart.
 *
 * Two input modes:
 *   1. `points` — an array of numbers (preferred when you have raw data,
 *      e.g. `GradeTrend.recent`).
 *   2. `bars` — a string of Unicode block characters from the backend
 *      (▁▂▃▄▅▆▇█); parsed into 0..7 heights. Fallback for when the
 *      backend hasn't been upgraded to send raw points yet.
 *
 * Sized for inline use (default 80×16 px). Stroke + dot color follow
 * `tone`; defaults to current text color.
 */
import { useMemo } from "react";

type Tone = "default" | "blue" | "red" | "green" | "amber" | "purple";

const TONE_COLOR: Record<Tone, string> = {
  default: "currentColor",
  blue:   "oklch(48% 0.17 255)",
  red:    "oklch(50% 0.18 25)",
  green:  "oklch(50% 0.13 150)",
  amber:  "oklch(55% 0.14 60)",
  purple: "oklch(40% 0.22 290)",
};

const BARS_TO_HEIGHT: Record<string, number> = {
  "▁": 0, "▂": 1, "▃": 2, "▄": 3, "▅": 4, "▆": 5, "▇": 6, "█": 7,
};

function parseBars(bars: string): number[] {
  return [...bars].map((c) => BARS_TO_HEIGHT[c] ?? 0);
}

export type SparklineProps = {
  points?: number[];
  bars?: string;
  width?: number;
  height?: number;
  tone?: Tone;
  /** Show a faint horizontal baseline at the min value. */
  baseline?: boolean;
  /** Title text (HTML title attr) — appears on hover. */
  title?: string;
  className?: string;
};

export function Sparkline({
  points,
  bars,
  width = 80,
  height = 16,
  tone = "default",
  baseline = true,
  title,
  className = "",
}: SparklineProps) {
  const series = useMemo<number[]>(() => {
    if (points && points.length > 0) return points;
    if (bars) return parseBars(bars);
    return [];
  }, [points, bars]);

  if (series.length === 0) return null;

  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const stepX = series.length > 1 ? width / (series.length - 1) : width;
  const padY = 2; // top/bottom padding so dot doesn't clip
  const usableH = height - padY * 2;

  const xy = series.map((v, i) => {
    const x = i * stepX;
    const y = height - padY - ((v - min) / range) * usableH;
    return [x, y];
  });
  const path = xy
    .map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`))
    .join(" ");
  const last = xy[xy.length - 1];
  const color = TONE_COLOR[tone];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      role="img"
      aria-label={title || `Trend of ${series.length} points`}
    >
      {title && <title>{title}</title>}
      {baseline && (
        <line
          x1={0}
          y1={height - padY}
          x2={width}
          y2={height - padY}
          stroke="currentColor"
          strokeOpacity={0.12}
          strokeWidth={1}
        />
      )}
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={1.4}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={last[0]} cy={last[1]} r={2.2} fill={color} />
    </svg>
  );
}
