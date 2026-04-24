/** Date formatting helpers. All inputs are ISO strings (YYYY-MM-DD or full
 * timestamp). Output is human-friendly: "Today", "Tomorrow", "Fri 25 Apr",
 * "3 days ago". All day-arithmetic is anchored to IST so a parent
 * on a different timezone still sees the same "Today". */

import { todayISOInIST } from "./ist";

const SHORT_WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SHORT_MONTH = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Parse an ISO date/timestamp into a Date.
 *
 *  - Pure `YYYY-MM-DD` → local midnight on that day (calendar semantics).
 *  - Timestamp WITH an explicit offset (`Z`, `+HH:MM`, `-HH:MM`) → respected.
 *  - Timestamp WITHOUT an offset (our backend returns these for
 *    DateTime(timezone=True) columns on SQLite) → treated as UTC.
 *
 *  The last clause is what fixes "synced 6h ago" mis-reports on IST —
 *  without it, `new Date("2026-04-24T06:30:00")` was being parsed as
 *  local IST time, inflating the age by the IST offset. */
function parseLocal(iso: string): Date | null {
  if (!iso) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  const hasTzOffset = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
  const normalized = hasTzOffset ? iso : iso + "Z";
  const d = new Date(normalized);
  return isNaN(d.getTime()) ? null : d;
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/** Day-difference (today-in-IST minus date) in integer days. Negative = future.
 *  The IST anchor makes the labels stable regardless of the browser's
 *  timezone — a parent using the app from a phone set to a different
 *  zone still sees "Today" for the IST today. */
function daysDiff(target: Date, today?: Date): number {
  if (!today) {
    const [y, m, d] = todayISOInIST().split("-").map(Number);
    today = new Date(y, m - 1, d);
  }
  const t = startOfDay(today).getTime();
  const x = startOfDay(target).getTime();
  return Math.round((t - x) / (24 * 60 * 60 * 1000));
}

/** Format an assignment/message due date.
 *   Today / Tomorrow / Yesterday / N days ago / In N days / Fri 25 Apr
 *
 *  Options:
 *    absolute: always use 'Fri 25 Apr' regardless of proximity
 */
export function formatDate(
  iso: string | null | undefined,
  opts: { absolute?: boolean } = {},
): string {
  if (!iso) return "—";
  const d = parseLocal(iso);
  if (!d) return iso;
  const diff = daysDiff(d);
  if (!opts.absolute) {
    if (diff === 0) return "Today";
    if (diff === 1) return "Yesterday";
    if (diff === -1) return "Tomorrow";
    if (diff > 0 && diff <= 6) return `${diff} days ago`;
    if (diff < 0 && diff >= -6) return `In ${-diff} days · ${SHORT_WEEKDAY[d.getDay()]}`;
  }
  const thisYear = new Date().getFullYear();
  const wd = SHORT_WEEKDAY[d.getDay()];
  const dd = d.getDate();
  const mon = SHORT_MONTH[d.getMonth()];
  const yr = d.getFullYear();
  if (yr === thisYear) return `${wd} ${dd} ${mon}`;
  return `${wd} ${dd} ${mon} ${yr}`;
}

/** Format an absolute date (no "Today"/"Yesterday" collapsing) — useful
 *  when you always want "25 Apr" style, e.g. in timelines. */
export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseLocal(iso);
  if (!d) return iso;
  const thisYear = new Date().getFullYear();
  const dd = d.getDate();
  const mon = SHORT_MONTH[d.getMonth()];
  const yr = d.getFullYear();
  return yr === thisYear ? `${dd} ${mon}` : `${dd} ${mon} ${yr}`;
}

/** Format as dd-mmm-yy — e.g. "25-Apr-26". Used on dense historical
 *  tables (grades, audit logs) where scannability beats friendliness. */
export function formatDDMMMYY(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseLocal(iso);
  if (!d) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mon = SHORT_MONTH[d.getMonth()];
  const yy = String(d.getFullYear() % 100).padStart(2, "0");
  return `${dd}-${mon}-${yy}`;
}

/** dd-mmm-yy HH:MM — same density for timestamps (local time). */
export function formatDDMMMYYTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseLocal(iso);
  if (!d) return iso;
  const base = formatDDMMMYY(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${base} ${hh}:${mi}`;
}

/** Format a timestamp as short "Apr 25 · 14:32" (local time). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseLocal(iso);
  if (!d) return iso;
  const dd = d.getDate();
  const mon = SHORT_MONTH[d.getMonth()];
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${dd} ${mon} · ${hh}:${mm}`;
}

/** Relative phrase — "3 days ago" / "in 2 days" / "just now" for recent times. */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseLocal(iso);
  if (!d) return iso;
  const now = new Date();
  const ms = now.getTime() - d.getTime();
  const absMs = Math.abs(ms);
  const future = ms < 0;
  if (absMs < 60 * 1000) return "just now";
  if (absMs < 60 * 60 * 1000) {
    const mins = Math.round(absMs / 60000);
    return future ? `in ${mins} min` : `${mins} min ago`;
  }
  if (absMs < 24 * 60 * 60 * 1000) {
    const hrs = Math.round(absMs / (60 * 60 * 1000));
    return future ? `in ${hrs}h` : `${hrs}h ago`;
  }
  const dys = Math.round(absMs / (24 * 60 * 60 * 1000));
  if (dys < 14) return future ? `in ${dys}d` : `${dys}d ago`;
  return formatDateShort(iso);
}
