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
  // Slimmed: dropped the ring-4 glow (it gave each pellet a 4-deep
  // halo that dominated the kid header). Now reads as a flat chip
  // with the canonical chip colour vocab. Anomalous gets a tiny
  // amber pulse via the chip-amber tone instead of a separate badge.
  const cls =
    tone === "green"  ? "chip-emerald"
    : tone === "amber"  ? "chip-amber"
    : tone === "red"    ? "chip-red"
    : "chip-gray";

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
      className={cls + " cursor-pointer hover:opacity-80"}
      title={tooltip}
      aria-label={`Recent grade: ${pellet.subject} ${pellet.pct.toFixed(0)}%${
        pellet.anomalous ? " (off-trend)" : ""
      }`}
    >
      <span aria-hidden className="mr-1">{arrow}</span>
      <span>{pellet.subject ?? "—"}</span>
      <span className="font-semibold ml-1">
        {pellet.score_text ?? `${pellet.pct.toFixed(0)}%`}
      </span>
      {/* Trailing anomaly mark only when the leading arrow isn't already
          a warning — otherwise the same ⚠ shows twice on red anomalous
          pellets. */}
      {pellet.anomalous && tone !== "red" && (
        <span aria-hidden className="ml-1">⚠</span>
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
