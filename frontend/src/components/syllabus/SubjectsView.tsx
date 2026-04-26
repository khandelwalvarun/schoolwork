/**
 * SubjectsView — Tab 1 of the Syllabus redesign.
 *
 * Per-subject row × per-cycle column. Each cycle cell is a single
 * stacked horizontal bar where segments are width-proportional to the
 * count of topics in each mastery state — not a row of anonymous dots
 * (the earlier dot grid lost each topic's identity and forced you to
 * hover-decode the page).
 *
 *   English  EN  ▓▓▓▓▓▓▓▓▓▓ ▓▓▓▓▓░░░░░ ▓▓▓░░░░░░░ ░░░░░░░░░░  12/15 ↗
 *   Hindi    हि ▓▓▓▓░░░░░░ ▓▓▓░░░░░░░ ▓░░░░░░░░░ ░░░░░░░░░░   7/12 →
 *
 * Click a bar → expands inline to show topic names + states + portfolio.
 * Click a topic in the expansion → opens TopicDetailPanel.
 * Hover × on a subject row → hides the subject (per-kid; restore in Settings).
 *
 * The mastery palette (mastered/proficient/familiar/attempted/decaying)
 * is the same one used everywhere else, so the bar reads as a quick
 * "how much green vs red" question.
 *
 * Today-line: a thin vertical mark inside the current cycle's bar at
 * the proportional position — "we're 22 days into a 60-day cycle, so
 * the line sits ~37% across this cell."
 */
import { useMemo, useState } from "react";
import {
  LanguageCode,
  SyllabusCycleFull,
  SyllabusDoc,
  TopicStateRow,
} from "../../api";
import { MasteryPelletFromRow, CoverageStatus } from "../MasteryPellet";
import { PortfolioBadge } from "../PortfolioBadge";
import {
  filterTopic,
  langOf,
  SyllabusFilterState,
} from "../SyllabusFilters";

type Props = {
  syllabus: SyllabusDoc;
  states: TopicStateRow[];
  childId: number;
  todayISO: string;
  filters: SyllabusFilterState;
  onTopicClick: (subject: string, topic: string) => void;
  isSubjectHidden: (subject: string) => boolean;
  onHideSubject: (subject: string) => void;
};

const LANG_PILL: Record<NonNullable<LanguageCode>, { label: string; tone: string }> = {
  en: { label: "EN",      tone: "border-blue-300 text-blue-800 bg-blue-50" },
  hi: { label: "हिन्दी", tone: "border-amber-300 text-amber-800 bg-amber-50" },
  sa: { label: "संस्कृत", tone: "border-purple-300 text-purple-800 bg-purple-50" },
};

/** Stacked-bar segment colours, in fixed precedence order so legends
 *  align across rows. Same OKLCH values as the pellet palette. */
const SEG: Array<{
  key: "mastered" | "proficient" | "familiar" | "attempted" | "decaying" | "none";
  label: string;
  color: string;
}> = [
  { key: "mastered",   label: "mastered",   color: "oklch(60% 0.13 150)" },
  { key: "proficient", label: "proficient", color: "oklch(60% 0.16 255)" },
  { key: "familiar",   label: "familiar",   color: "oklch(70% 0.13 60)"  },
  { key: "attempted",  label: "attempted",  color: "oklch(70% 0.005 280)"},
  { key: "decaying",   label: "decaying",   color: "oklch(60% 0.18 25)"  },
  { key: "none",       label: "not yet",    color: "oklch(94% 0.005 250)"},
];

function dayPosInCycle(c: SyllabusCycleFull, todayISO: string): number | null {
  if (todayISO < c.start || todayISO > c.end) return null;
  const start = new Date(c.start + "T00:00:00").getTime();
  const end = new Date(c.end + "T00:00:00").getTime();
  const now = new Date(todayISO + "T00:00:00").getTime();
  return Math.max(0, Math.min(1, (now - start) / Math.max(end - start, 1)));
}

function trendArrow(rows: TopicStateRow[]): string {
  if (rows.length === 0) return "—";
  const dec = rows.filter((r) => r.state === "decaying").length;
  if (dec >= 2) return "↘";
  const masteredShare = rows.filter((r) => r.state === "mastered").length / rows.length;
  if (masteredShare >= 0.6) return "↗";
  return "→";
}

type CycleBucket = Record<typeof SEG[number]["key"], number>;

function bucketTopics(
  topics: string[],
  subject: string,
  stateBy: Map<string, TopicStateRow>,
): CycleBucket {
  const b: CycleBucket = {
    mastered: 0, proficient: 0, familiar: 0, attempted: 0, decaying: 0, none: 0,
  };
  for (const t of topics) {
    const s = stateBy.get(`${subject}::${t}`);
    const k = (s?.state ?? "none") as typeof SEG[number]["key"];
    b[k] = (b[k] ?? 0) + 1;
  }
  return b;
}

function MasteryBar({
  bucket,
  total,
  todayPos,
  isCurrent,
}: {
  bucket: CycleBucket;
  total: number;
  todayPos: number | null;
  isCurrent: boolean;
}) {
  if (total === 0) {
    return (
      <div className="text-[10px] text-gray-400 italic px-1">empty</div>
    );
  }
  return (
    <div
      className={
        "relative h-5 rounded overflow-hidden flex border " +
        (isCurrent
          ? "border-purple-300 ring-1 ring-purple-200"
          : "border-gray-200")
      }
      title={SEG.filter((s) => bucket[s.key] > 0)
        .map((s) => `${bucket[s.key]} ${s.label}`)
        .join(", ")}
    >
      {SEG.map((s) => {
        const n = bucket[s.key];
        if (n === 0) return null;
        const pct = (n / total) * 100;
        return (
          <span
            key={s.key}
            style={{
              width: `${pct}%`,
              background: s.color,
            }}
            aria-label={`${n} ${s.label}`}
          />
        );
      })}
      {todayPos !== null && (
        <span
          aria-hidden
          className="absolute top-0 bottom-0 pointer-events-none"
          style={{
            left: `${todayPos * 100}%`,
            width: 2,
            background: "oklch(40% 0.22 290)",
            boxShadow: "0 0 0 1px white",
          }}
        />
      )}
    </div>
  );
}

export function SubjectsView({
  syllabus,
  states,
  childId,
  todayISO,
  filters,
  onTopicClick,
  isSubjectHidden,
  onHideSubject,
}: Props) {
  const stateBy = useMemo(() => {
    const m = new Map<string, TopicStateRow>();
    for (const r of states) m.set(`${r.subject}::${r.topic}`, r);
    return m;
  }, [states]);

  const subjects = useMemo(() => {
    const s = new Set<string>();
    for (const c of syllabus.cycles) {
      for (const subj of Object.keys(c.topics_by_subject || {})) s.add(subj);
    }
    return Array.from(s)
      .filter((subj) => !isSubjectHidden(subj))
      .sort();
  }, [syllabus, isSubjectHidden]);

  const [expanded, setExpanded] = useState<{
    subject: string;
    cycleIdx: number;
  } | null>(null);

  const gridStyle = {
    gridTemplateColumns: `11rem repeat(${syllabus.cycles.length}, 1fr) 6rem`,
  };

  return (
    <div className="space-y-2">
      {/* Cycle header row */}
      <div
        className="grid items-baseline gap-3 text-[11px] text-gray-500 px-3"
        style={gridStyle}
      >
        <span></span>
        {syllabus.cycles.map((c) => {
          const here = c.start <= todayISO && todayISO <= c.end;
          return (
            <div
              key={c.name}
              className={`min-w-0 ${here ? "text-purple-800 font-semibold" : ""}`}
            >
              <div className="truncate">
                {c.name} {here && <span aria-hidden>★</span>}
              </div>
              <div className="text-[10px] text-gray-400 truncate">
                {c.start.slice(5)} → {c.end.slice(5)}
              </div>
            </div>
          );
        })}
        <span className="text-right">Mastered · trend</span>
      </div>

      {/* Inline mastery legend so the bars are decoded immediately. */}
      <div className="flex items-center gap-3 text-[10px] text-gray-500 px-3 -mt-1 mb-1 flex-wrap">
        {SEG.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1">
            <span
              aria-hidden
              className="inline-block w-3 h-3 rounded-sm"
              style={{ background: s.color }}
            />
            {s.label}
          </span>
        ))}
        <span className="text-purple-700 inline-flex items-center gap-1">
          <span
            aria-hidden
            className="inline-block w-px h-3"
            style={{ background: "oklch(40% 0.22 290)" }}
          />
          today
        </span>
      </div>

      {subjects.map((subject) => {
        const lc = langOf(subject);
        const langMeta = lc ? LANG_PILL[lc] : null;
        const allRows = states.filter((r) => r.subject === subject);
        const masteredN = allRows.filter((r) => r.state === "mastered").length;
        const totalRowsN = allRows.length;
        const arrow = trendArrow(allRows);

        return (
          <section
            key={subject}
            className="surface px-3 py-2.5 group"
          >
            <div className="grid items-center gap-3" style={gridStyle}>
              <div className="flex items-center gap-1.5 min-w-0">
                <span
                  className="font-semibold text-sm text-gray-800 truncate"
                  title={subject}
                >
                  {subject}
                </span>
                {langMeta && (
                  <span
                    className={`inline-flex items-center px-1 py-0.5 rounded text-[9px] border ${langMeta.tone} flex-shrink-0`}
                  >
                    {langMeta.label}
                  </span>
                )}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onHideSubject(subject);
                  }}
                  title={`Hide "${subject}" — restore from Settings`}
                  aria-label={`Hide ${subject}`}
                  className="ml-auto opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-600 text-base leading-none flex-shrink-0 transition-opacity"
                >
                  ×
                </button>
              </div>

              {syllabus.cycles.map((c, cycleIdx) => {
                const topics = c.topics_by_subject?.[subject] || [];
                const visibleTopics = topics.filter((t) => {
                  const ms = stateBy.get(`${subject}::${t}`);
                  const cov = (c.topic_status?.[subject]?.[t]?.status ??
                    null) as
                    | "covered"
                    | "in_progress"
                    | "delayed"
                    | "skipped"
                    | null;
                  return filterTopic(filters, langOf, subject, ms?.state ?? null, cov);
                });
                const bucket = bucketTopics(visibleTopics, subject, stateBy);
                const total = visibleTopics.length;
                const dayPos = dayPosInCycle(c, todayISO);
                const isCurrent =
                  c.start <= todayISO && todayISO <= c.end;
                const isExpanded =
                  expanded?.subject === subject &&
                  expanded?.cycleIdx === cycleIdx;

                return (
                  <button
                    key={c.name}
                    type="button"
                    onClick={() =>
                      setExpanded(
                        isExpanded ? null : { subject, cycleIdx },
                      )
                    }
                    className={`min-w-0 text-left ${
                      isExpanded ? "ring-1 ring-purple-300 rounded" : ""
                    }`}
                    aria-expanded={isExpanded}
                  >
                    <MasteryBar
                      bucket={bucket}
                      total={total}
                      todayPos={dayPos}
                      isCurrent={isCurrent}
                    />
                    <div className="text-[10px] text-gray-500 mt-0.5 truncate">
                      {total > 0 ? `${total} topic${total === 1 ? "" : "s"}` : "—"}
                    </div>
                  </button>
                );
              })}

              <div className="text-right text-xs text-gray-600 whitespace-nowrap">
                <span className="font-mono">
                  {masteredN}/{totalRowsN || "?"}
                </span>
                <span className="ml-1.5 text-base" aria-hidden>{arrow}</span>
              </div>
            </div>

            {expanded?.subject === subject &&
              (() => {
                const c = syllabus.cycles[expanded.cycleIdx];
                if (!c) return null;
                const topics = c.topics_by_subject?.[subject] || [];
                return (
                  <div className="mt-3 pt-2 border-t border-[color:var(--line-soft)]">
                    <div className="text-[11px] text-gray-500 mb-1">
                      {c.name} · {topics.length} topic{topics.length === 1 ? "" : "s"}
                    </div>
                    <ul className="space-y-1">
                      {topics.map((t) => {
                        const ms = stateBy.get(`${subject}::${t}`);
                        const cov = (c.topic_status?.[subject]?.[t]?.status ??
                          null) as CoverageStatus;
                        return (
                          <li
                            key={t}
                            className="flex items-center gap-2 text-sm"
                          >
                            <MasteryPelletFromRow row={ms} coverage={cov} />
                            <button
                              type="button"
                              onClick={() => onTopicClick(subject, t)}
                              className="flex-1 text-left text-gray-800 hover:underline truncate"
                            >
                              {t}
                            </button>
                            <PortfolioBadge
                              childId={childId}
                              subject={subject}
                              topic={t}
                            />
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })()}
          </section>
        );
      })}

      {subjects.length === 0 && (
        <div className="surface p-6 text-center text-sm text-gray-500">
          All subjects are hidden for this kid. Restore from Settings →
          Hidden subjects.
        </div>
      )}
    </div>
  );
}
