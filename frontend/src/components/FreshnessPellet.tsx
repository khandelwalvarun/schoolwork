import { FreshGradePellet } from "../api";

/** Renders next to the kid's name on Today / ChildBoard / ChildDetail.
 *  The visual signal is "this just happened" — soft glow + tone-coloured
 *  border. Anomalous grades stay visible past the 48h freshness window.
 *
 *  Click handler is optional. When provided, parent components usually
 *  open the AuditDrawer for `pellet.item_id`.
 */
export function FreshnessPellet({
  pellet,
  onClick,
}: {
  pellet: FreshGradePellet;
  onClick?: (itemId: number) => void;
}) {
  const tone = pellet.tone;
  const cls =
    tone === "green"
      ? "bg-emerald-50 text-emerald-800 border-emerald-300 ring-emerald-100"
      : tone === "amber"
      ? "bg-amber-50 text-amber-800 border-amber-300 ring-amber-100"
      : tone === "red"
      ? "bg-rose-50 text-rose-800 border-rose-300 ring-rose-100"
      : "bg-gray-50 text-gray-700 border-gray-300 ring-gray-100";

  const arrow =
    tone === "green" ? "✓"
    : tone === "amber" ? "↗"
    : tone === "red" ? "⚠"
    : "•";

  const ageLabel = (() => {
    const h = pellet.hours_ago;
    if (h === null || h === undefined) return "";
    if (h < 1) return "just now";
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return d === 1 ? "yesterday" : `${d}d ago`;
  })();

  const tooltip = [
    pellet.title,
    pellet.score_text || `${pellet.pct.toFixed(0)}%`,
    pellet.anomalous ? "off-trend — see anomaly explainer" : null,
    ageLabel || null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={onClick ? () => onClick(pellet.item_id) : undefined}
      className={
        "inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 " +
        "rounded-full border ring-4 transition-shadow cursor-pointer hover:ring-[6px] " +
        cls
      }
      title={tooltip}
      aria-label={`Recent grade: ${pellet.subject} ${pellet.pct.toFixed(0)}%${
        pellet.anomalous ? " (off-trend)" : ""
      }`}
    >
      <span aria-hidden>{arrow}</span>
      <span>{pellet.subject ?? "—"}</span>
      <span className="font-semibold">
        {pellet.score_text ?? `${pellet.pct.toFixed(0)}%`}
      </span>
      {ageLabel && (
        <span className="text-[10px] font-normal opacity-75">· {ageLabel}</span>
      )}
      {pellet.anomalous && (
        <span className="text-[10px] font-normal opacity-75">· anomaly</span>
      )}
    </button>
  );
}

export function FreshnessPelletStrip({
  pellets,
  onClick,
}: {
  pellets: FreshGradePellet[] | undefined;
  onClick?: (itemId: number) => void;
}) {
  if (!pellets || pellets.length === 0) {
    return (
      <span className="text-xs text-gray-400 italic">
        No new grades in the last 48h
      </span>
    );
  }
  return (
    <div className="inline-flex items-center gap-2 flex-wrap">
      {pellets.map((p) => (
        <FreshnessPellet key={p.item_id} pellet={p} onClick={onClick} />
      ))}
    </div>
  );
}
