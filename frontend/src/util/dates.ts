/** Date formatting helpers. All inputs are ISO strings (YYYY-MM-DD or full
 * timestamp). Output is human-friendly: "Today", "Tomorrow", "Fri 25 Apr",
 * "3 days ago". */

const SHORT_WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SHORT_MONTH = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Parse an ISO date (YYYY-MM-DD or timestamp) into a local Date.
 * For date-only strings we anchor at local midnight to avoid TZ surprises. */
function parseLocal(iso: string): Date | null {
  if (!iso) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/** Day-difference (today - date) in integer days. Negative = future. */
function daysDiff(target: Date, today = new Date()): number {
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
