/**
 * Persistent legend strip at the bottom of the Syllabus page.
 * Removes the hover-tax of decoding pellet colors.
 */
import { MasteryPellet } from "./MasteryPellet";

const ITEMS: Array<{ state: "attempted" | "familiar" | "proficient" | "mastered" | "decaying" | null; label: string }> = [
  { state: null,         label: "not yet" },
  { state: "attempted",  label: "attempted" },
  { state: "familiar",   label: "familiar" },
  { state: "proficient", label: "proficient" },
  { state: "mastered",   label: "mastered" },
  { state: "decaying",   label: "decaying" },
];

const COVERAGE: Array<{ key: "covered" | "in_progress" | "delayed" | "skipped"; label: string }> = [
  { key: "covered",     label: "covered" },
  { key: "in_progress", label: "now teaching" },
  { key: "delayed",     label: "delayed" },
  { key: "skipped",     label: "skipped" },
];

export function MasteryLegend() {
  return (
    <div className="legend-strip">
      <span className="text-gray-500 font-semibold">Mastery</span>
      {ITEMS.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1 text-gray-600">
          <MasteryPellet state={it.state} />
          {it.label}
        </span>
      ))}
      <span className="text-gray-300">·</span>
      <span className="text-gray-500 font-semibold">Coverage</span>
      {COVERAGE.map((c) => (
        <span key={c.key} className="inline-flex items-center gap-1 text-gray-600">
          <span
            className={`pellet-coverage cov-${c.key}`}
            aria-hidden
            style={{ "--cov-color": undefined } as React.CSSProperties}
          >
            <span className="pellet pellet--none" aria-hidden />
          </span>
          {c.label}
        </span>
      ))}
    </div>
  );
}
