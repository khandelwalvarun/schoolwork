/**
 * Tray — a compact collapsible strip with a tone-tinted header.
 *
 * Replaces four copy-pasted versions (AnomalyTray, WorthAChatTray,
 * ShakyTopicsTray, ClassworkTodayStrip), each of which had subtly
 * different interaction conventions. Centralising forces one mental
 * model: small bar at the top, click to expand, single-line summary
 * always visible.
 *
 * Defaults follow the calm-tech rule: when there's a lot to say (N>1)
 * the tray collapses; when there's only one thing it auto-expands —
 * no point hiding a single line behind a chevron.
 *
 * Tone selects header colour from the documented semantic precedence
 * in styles.css (red = blocker, amber = attention, violet = parent-
 * flagged, gray = neutral). Don't add new tones here — extend the
 * precedence comment block first.
 */
import { ReactNode, useState } from "react";

export type TrayTone = "red" | "amber" | "emerald" | "blue" | "violet" | "purple" | "gray";

const TONE_HEADER: Record<TrayTone, { wrap: string; chev: string; meta: string }> = {
  red:     { wrap: "border-red-200 bg-red-50/60 text-red-900 hover:bg-red-50",
             chev: "text-red-700", meta: "text-red-700/70" },
  amber:   { wrap: "border-amber-200 bg-amber-50/60 text-amber-900 hover:bg-amber-50",
             chev: "text-amber-700", meta: "text-amber-700/70" },
  emerald: { wrap: "border-emerald-200 bg-emerald-50/60 text-emerald-900 hover:bg-emerald-50",
             chev: "text-emerald-700", meta: "text-emerald-700/70" },
  blue:    { wrap: "border-blue-200 bg-blue-50/60 text-blue-900 hover:bg-blue-50",
             chev: "text-blue-700", meta: "text-blue-700/70" },
  violet:  { wrap: "border-violet-200 bg-violet-50/60 text-violet-900 hover:bg-violet-50",
             chev: "text-violet-700", meta: "text-violet-700/70" },
  purple:  { wrap: "border-purple-200 bg-purple-50/60 text-purple-900 hover:bg-purple-50",
             chev: "text-purple-700", meta: "text-purple-700/70" },
  gray:    { wrap: "border-gray-200 bg-gray-50/60 text-gray-900 hover:bg-gray-50",
             chev: "text-gray-500", meta: "text-gray-500" },
};

const TONE_BORDER: Record<TrayTone, string> = {
  red:     "border-red-200",
  amber:   "border-amber-200",
  emerald: "border-emerald-200",
  blue:    "border-blue-200",
  violet:  "border-violet-200",
  purple:  "border-purple-200",
  gray:    "border-gray-200",
};

export function Tray({
  title,
  count,
  summary,
  tone = "gray",
  defaultCollapsed,
  forceExpanded,
  rightSlot,
  children,
  className = "",
}: {
  /** Bold title shown in the header. e.g. "Off-trend grades", "Worth a chat". */
  title: ReactNode;
  /** Numeric count shown after the title. Hidden when undefined. */
  count?: number;
  /** Short text shown after the count. Hidden when undefined. */
  summary?: string;
  /** Tone-tinted header colour. See semantic precedence in styles.css. */
  tone?: TrayTone;
  /** Default-collapsed state. If undefined, auto-collapsed when count > 1. */
  defaultCollapsed?: boolean;
  /** Force expanded — used when there's only one item to show. */
  forceExpanded?: boolean;
  /** Optional right-aligned action slot in the header (e.g. "show dismissed"). */
  rightSlot?: ReactNode;
  /** Body content rendered when expanded. */
  children: ReactNode;
  className?: string;
}) {
  const computedDefaultCollapsed =
    defaultCollapsed ?? (typeof count === "number" ? count > 1 : false);
  const [collapsed, setCollapsed] = useState(computedDefaultCollapsed);
  const expanded = forceExpanded || !collapsed;

  const t = TONE_HEADER[tone];

  return (
    <section className={"mb-4 text-body " + className}>
      <button
        type="button"
        onClick={() => setCollapsed((x) => !x)}
        className={
          "w-full flex items-center gap-2 px-3 py-1.5 rounded border transition-colors " +
          t.wrap
        }
        aria-expanded={expanded}
      >
        <span
          className={
            "inline-block transition-transform " +
            t.chev +
            " " +
            (expanded ? "rotate-90" : "")
          }
          aria-hidden
        >
          ▶
        </span>
        <span className="font-medium">
          {title}
          {typeof count === "number" && <> · {count}</>}
        </span>
        {summary && <span className={"text-meta " + t.meta}>{summary}</span>}
        {rightSlot && <span className="ml-auto">{rightSlot}</span>}
      </button>
      {expanded && (
        <div className="mt-1 ml-2">
          {children}
        </div>
      )}
    </section>
  );
}

/** Helper border-class lookup for tray rows. Children render their
 *  own <ul>/<li> using this class for the left-rule accent. */
export function trayLineClass(tone: TrayTone): string {
  return "py-1 pl-2 border-l-2 " + TONE_BORDER[tone];
}

