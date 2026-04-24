/** IST-canonical date helpers. Parents live in India; the server is IST.
 * A phone/laptop in a different zone must still see the SAME "today" as
 * the rest of the system. Never use `new Date()` for date arithmetic in
 * app logic — route it through here.
 *
 * Strategy: format a Date as YYYY-MM-DD using the "Asia/Kolkata" formatter,
 * then parse back as a local anchor at midnight for day-arithmetic. That
 * yields the IST calendar date regardless of the runtime's zone.
 */

const IST_FMT = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function pad(n: number): string { return String(n).padStart(2, "0"); }

/** Today in IST as "YYYY-MM-DD". */
export function todayISOInIST(): string {
  // Intl formatter gives dd/mm/yyyy in en-GB — flip it.
  const parts = IST_FMT.formatToParts(new Date());
  const d = parts.find((p) => p.type === "day")?.value ?? "01";
  const m = parts.find((p) => p.type === "month")?.value ?? "01";
  const y = parts.find((p) => p.type === "year")?.value ?? "1970";
  return `${y}-${m}-${d}`;
}

/** IST date `n` days from today, as "YYYY-MM-DD". */
export function daysFromTodayIST(n: number): string {
  const base = todayISOInIST();
  const [y, m, d] = base.split("-").map(Number);
  // Anchor at noon UTC-12-worth to avoid DST/tz ambiguity; arithmetic on
  // pure day counts is fine because we only care about calendar days.
  const dt = new Date(Date.UTC(y, m - 1, d) + n * 24 * 60 * 60 * 1000);
  return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
}

/** Next Saturday in IST as "YYYY-MM-DD". If today is Saturday, returns
 * the Saturday a week out. */
export function nextWeekendIST(): string {
  const iso = todayISOInIST();
  const [y, m, d] = iso.split("-").map(Number);
  // Day-of-week using UTC anchor (consistent across runtimes).
  const anchor = new Date(Date.UTC(y, m - 1, d));
  const dow = anchor.getUTCDay(); // 0=Sun .. 6=Sat
  const delta = ((6 - dow + 7) % 7) || 7;
  return daysFromTodayIST(delta);
}

/** Is an ISO date string (YYYY-MM-DD) strictly after today-in-IST? */
export function isFutureIST(iso: string | null | undefined): boolean {
  if (!iso) return false;
  return iso > todayISOInIST();
}
