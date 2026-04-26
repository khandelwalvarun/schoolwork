/**
 * SubjectsView — Tab 1 of the Syllabus redesign.
 *
 * Layout: subject-as-row, cycles-as-columns. The view that answers
 * "how is each subject going?" at a glance.
 *
 *   English  EN  [LC1 pellets ...]  [LC2 ...]  [LC3 ...]  [LC4★ ...]  12/15 mastered
 *   Hindi    हि  ...
 *
 * Each cycle cell is a horizontal stack of small mastery pellets — one
 * per topic — colored by mastery state. The pellet's coverage strip
 * tints by the syllabus topic_status. The current cycle is marked with
 * a star + a today-line through it.
 *
 * Click a cell → expands inline to show the topic list with names +
 * mastery + portfolio badge + click-to-open detail panel.
 *
 * Click a single pellet → opens the TopicDetailPanel directly.
 */
import { useMemo, useState } from "react";
import {
  LanguageCode,
  SyllabusCycleFull,
  SyllabusDoc,
  TopicStateRow,
} from "../../api";
import { MasteryPelletFromRow } from "../MasteryPellet";
import {
  CoverageStatus,
} from "../MasteryPellet";
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
};

const LANG_PILL: Record<NonNullable<LanguageCode>, { label: string; tone: string }> = {
  en: { label: "EN",      tone: "border-blue-300 text-blue-800 bg-blue-50" },
  hi: { label: "हिन्दी", tone: "border-amber-300 text-amber-800 bg-amber-50" },
  sa: { label: "संस्कृत", tone: "border-purple-300 text-purple-800 bg-purple-50" },
};

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

export function SubjectsView({
  syllabus,
  states,
  childId,
  todayISO,
  filters,
  onTopicClick,
}: Props) {
  // Group topic states by subject for fast lookup.
  const stateBy = useMemo(() => {
    const m = new Map<string, TopicStateRow>();
    for (const r of states) m.set(`${r.subject}::${r.topic}`, r);
    return m;
  }, [states]);

  // The full set of subjects across all cycles.
  const subjects = useMemo(() => {
    const s = new Set<string>();
    for (const c of syllabus.cycles) {
      for (const subj of Object.keys(c.topics_by_subject || {})) s.add(subj);
    }
    return Array.from(s).sort();
  }, [syllabus]);

  const [expanded, setExpanded] = useState<{
    subject: string;
    cycleIdx: number;
  } | null>(null);

  return (
    <div className="space-y-2">
      {/* Cycle header row — shared scale across every subject row. */}
      <div className="grid items-end gap-2 text-[11px] text-gray-500 px-2"
           style={{ gridTemplateColumns: `9rem repeat(${syllabus.cycles.length}, 1fr) 8rem` }}>
        <span></span>
        {syllabus.cycles.map((c) => {
          const here = c.start <= todayISO && todayISO <= c.end;
          return (
            <div key={c.name} className={`flex items-baseline gap-1 ${here ? "text-purple-800 font-semibold" : ""}`}>
              <span>{c.name}</span>
              {here && <span aria-hidden>★</span>}
              <span className="text-gray-400">· {c.start.slice(5)} → {c.end.slice(5)}</span>
            </div>
          );
        })}
        <span className="text-right">Mastery · trend</span>
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
            className="surface px-3 py-2.5"
          >
            <div className="grid items-center gap-2"
                 style={{ gridTemplateColumns: `9rem repeat(${syllabus.cycles.length}, 1fr) 8rem` }}>
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="font-semibold text-sm text-gray-800 truncate" title={subject}>
                  {subject}
                </span>
                {langMeta && (
                  <span
                    className={`inline-flex items-center px-1 py-0.5 rounded text-[9px] border ${langMeta.tone} flex-shrink-0`}
                  >
                    {langMeta.label}
                  </span>
                )}
              </div>

              {syllabus.cycles.map((c, cycleIdx) => {
                const topics = c.topics_by_subject?.[subject] || [];
                const dayPos = dayPosInCycle(c, todayISO);
                const isExpanded =
                  expanded?.subject === subject && expanded?.cycleIdx === cycleIdx;

                return (
                  <button
                    key={c.name}
                    type="button"
                    onClick={() =>
                      setExpanded(
                        isExpanded
                          ? null
                          : { subject, cycleIdx },
                      )
                    }
                    className={`relative flex flex-wrap items-center gap-1 px-1.5 py-1 rounded text-left ${
                      isExpanded ? "bg-purple-50 ring-1 ring-purple-300" : "hover:bg-gray-50"
                    }`}
                    aria-expanded={isExpanded}
                    title={`${c.name}: ${topics.length} topic${topics.length === 1 ? "" : "s"}`}
                  >
                    {topics.length === 0 ? (
                      <span className="text-[10px] text-gray-400 italic">empty</span>
                    ) : (
                      topics.map((t) => {
                        const ms = stateBy.get(`${subject}::${t}`);
                        const cov =
                          (c.topic_status?.[subject]?.[t]?.status ??
                            null) as CoverageStatus;
                        if (
                          !filterTopic(
                            filters,
                            langOf,
                            subject,
                            ms?.state ?? null,
                            cov as
                              | "covered"
                              | "in_progress"
                              | "delayed"
                              | "skipped"
                              | null,
                          )
                        ) {
                          return null;
                        }
                        return (
                          <span
                            key={t}
                            onClick={(e) => {
                              e.stopPropagation();
                              onTopicClick(subject, t);
                            }}
                            className="cursor-pointer"
                          >
                            <MasteryPelletFromRow row={ms} coverage={cov} />
                          </span>
                        );
                      })
                    )}
                    {dayPos !== null && (
                      <span
                        aria-hidden
                        className="absolute top-0 bottom-0 w-px bg-purple-500/60 pointer-events-none"
                        style={{ left: `${dayPos * 100}%` }}
                      />
                    )}
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

            {expanded?.subject === subject && (() => {
              const c = syllabus.cycles[expanded.cycleIdx];
              if (!c) return null;
              const topics = c.topics_by_subject?.[subject] || [];
              return (
                <div className="mt-2 pt-2 border-t border-[color:var(--line-soft)]">
                  <div className="text-[11px] text-gray-500 mb-1">
                    {c.name} · {topics.length} topic{topics.length === 1 ? "" : "s"}
                  </div>
                  <ul className="space-y-1">
                    {topics.map((t) => {
                      const ms = stateBy.get(`${subject}::${t}`);
                      const cov =
                        (c.topic_status?.[subject]?.[t]?.status ??
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
    </div>
  );
}
