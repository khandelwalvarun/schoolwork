/**
 * MasteryPellet — single 14px dot tinted by mastery state.
 *
 * Used in two places:
 *   1. Inline in topic lists (no coverage strip needed)
 *   2. Wrapped in a `.pellet-coverage` container that adds a 2px top-bar
 *      indicating the school's coverage status (covered / skipped /
 *      delayed / in_progress)
 *
 * The pellet itself is purely about MASTERY (what the kid knows).
 * The coverage strip is purely about TEACHING STATUS (whether the
 * school has gotten to it yet). Two orthogonal axes; never collapse.
 */
import { MasteryState, TopicStateRow } from "../api";

export type CoverageStatus =
  | "covered"
  | "in_progress"
  | "delayed"
  | "skipped"
  | null
  | undefined;

const STATE_LABELS: Record<NonNullable<MasteryState>, string> = {
  attempted:  "Attempted",
  familiar:   "Familiar (≥75%)",
  proficient: "Proficient (2× ≥75%)",
  mastered:   "Mastered (3× ≥85%)",
  decaying:   "Decaying — needs refresher",
};

const COV_LABELS: Record<NonNullable<CoverageStatus>, string> = {
  covered:     "Covered in class",
  in_progress: "Being taught now",
  delayed:     "Delayed",
  skipped:     "Skipped this cycle",
};

function pelletClass(state: MasteryState): string {
  if (!state) return "pellet pellet--none";
  return `pellet pellet--${state}`;
}

export function MasteryPellet({
  state,
  coverage,
  title,
  className,
}: {
  state: MasteryState;
  coverage?: CoverageStatus;
  title?: string;
  className?: string;
}) {
  const label = state ? STATE_LABELS[state] : "Not yet attempted";
  const covLabel = coverage ? COV_LABELS[coverage] : null;
  const tooltip =
    title ||
    (covLabel ? `${label}\n${covLabel}` : label);

  if (coverage) {
    return (
      <span
        className={`pellet-coverage cov-${coverage} ${className ?? ""}`}
        title={tooltip}
        aria-label={tooltip}
      >
        <span className={pelletClass(state)} aria-hidden />
      </span>
    );
  }

  return (
    <span
      className={`${pelletClass(state)} ${className ?? ""}`}
      title={tooltip}
      aria-label={tooltip}
    />
  );
}

/** Convenience overload — render from a TopicStateRow + an optional
 *  coverage status pulled from the syllabus. */
export function MasteryPelletFromRow({
  row,
  coverage,
}: {
  row: TopicStateRow | null | undefined;
  coverage?: CoverageStatus;
}) {
  const score = row?.last_score != null ? ` · ${row.last_score.toFixed(0)}%` : "";
  const attempts = row
    ? ` · ${row.attempt_count} item${row.attempt_count === 1 ? "" : "s"}`
    : "";
  const tooltip = row
    ? `${row.subject} — ${row.topic}\n${
        STATE_LABELS[row.state] ?? row.state
      }${score}${attempts}`
    : "Not yet attempted";
  return (
    <MasteryPellet
      state={row?.state ?? null}
      coverage={coverage}
      title={tooltip}
    />
  );
}
