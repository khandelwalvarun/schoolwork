/**
 * ListView — Tab 3 of the Syllabus redesign.
 *
 * The "show me everything" mode. Subject-grouped, all cycles flattened
 * into one scrollable column per subject. Closest in spirit to the
 * original page but with the pellet palette, filter strip, click-to-
 * open detail panel, and language chips.
 *
 * Useful for orientation on a new computer / first-time use; not the
 * daily driver. Tab 1 is the default.
 */
import { useMemo } from "react";
import {
  LanguageCode,
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

const LANG_PILL: Record<NonNullable<LanguageCode>, { label: string; tone: string }> = {
  en: { label: "EN",      tone: "border-blue-300 text-blue-800 bg-blue-50" },
  hi: { label: "हिन्दी", tone: "border-amber-300 text-amber-800 bg-amber-50" },
  sa: { label: "संस्कृत", tone: "border-purple-300 text-purple-800 bg-purple-50" },
};

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

export function ListView({
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

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {subjects.map((subject) => {
        const lc = langOf(subject);
        const langMeta = lc ? LANG_PILL[lc] : null;
        return (
          <section key={subject} className="surface p-3 group">
            <div className="flex items-center gap-2 mb-2">
              <span className="font-semibold text-gray-800">{subject}</span>
              {langMeta && (
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${langMeta.tone}`}
                >
                  {langMeta.label}
                </span>
              )}
              <button
                type="button"
                onClick={() => onHideSubject(subject)}
                title={`Hide "${subject}" — restore from Settings`}
                aria-label={`Hide ${subject}`}
                className="ml-auto opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-600 text-base leading-none transition-opacity"
              >
                ×
              </button>
            </div>

            <div className="space-y-3">
              {syllabus.cycles.map((c) => {
                const topics = c.topics_by_subject?.[subject] || [];
                if (topics.length === 0) return null;
                const here = c.start <= todayISO && todayISO <= c.end;

                const visible = topics.filter((t) => {
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
                if (visible.length === 0) return null;

                return (
                  <div key={c.name}>
                    <div className={`text-[11px] mb-1 ${here ? "text-purple-700 font-semibold" : "text-gray-500"}`}>
                      {c.name} {here && "★"}
                    </div>
                    <ul className="space-y-1">
                      {visible.map((t) => {
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
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
