import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, TopicStateRow } from "../api";
import ChildHeader from "../components/ChildHeader";
import { todayISOInIST } from "../util/ist";

/** Visual treatment for the per-topic mastery state. Tuned for OKLCH
 *  palette + colour-blind safe (paired with text label on hover). */
const STATE_DOT: Record<TopicStateRow["state"], { color: string; label: string }> = {
  attempted:  { color: "oklch(60% 0.005 280)",  label: "Attempted" },
  familiar:   { color: "oklch(55% 0.14 60)",    label: "Familiar (≥75%)" },
  proficient: { color: "oklch(48% 0.17 255)",   label: "Proficient (2× ≥75%)" },
  mastered:   { color: "oklch(50% 0.13 150)",   label: "Mastered (3× ≥85%)" },
  decaying:   { color: "oklch(55% 0.18 25)",    label: "Decaying (>30 d)" },
};

/** Phase 15: derive language from subject name. Mirrors backend
 *  services/language.py — kept in sync manually. */
function languageOf(subject: string | null | undefined): "en" | "hi" | "sa" | null {
  if (!subject) return null;
  const s = subject.toLowerCase();
  if (s.includes("sanskrit")) return "sa";
  if (s.includes("hindi")) return "hi";
  if (s.includes("english")) return "en";
  return null;
}

const LANG_CHIP: Record<"en" | "hi" | "sa", { label: string; tone: string }> = {
  en: { label: "EN", tone: "border-blue-300 text-blue-800 bg-blue-50" },
  hi: { label: "हिन्दी", tone: "border-amber-300 text-amber-800 bg-amber-50" },
  sa: { label: "संस्कृत", tone: "border-purple-300 text-purple-800 bg-purple-50" },
};

function LanguageChip({ subject }: { subject: string | null | undefined }) {
  const code = languageOf(subject);
  if (!code) return null;
  const { label, tone } = LANG_CHIP[code];
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ml-2 ${tone}`}
      title={`Language track: ${code === "en" ? "English" : code === "hi" ? "Hindi" : "Sanskrit"}`}
    >
      {label}
    </span>
  );
}

function MasteryDot({ row }: { row: TopicStateRow }) {
  const { color, label } = STATE_DOT[row.state];
  const score = row.last_score != null ? ` · ${row.last_score.toFixed(0)}%` : "";
  return (
    <span
      title={`${label}${score} · ${row.attempt_count} item${row.attempt_count === 1 ? "" : "s"}`}
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: 999,
        background: color,
      }}
      aria-label={`${row.state}${score}`}
    />
  );
}

export default function ChildSyllabus() {
  const { id } = useParams();
  const childId = Number(id);
  const { data: child } = useQuery({
    queryKey: ["child-detail", childId],
    queryFn: () => api.childDetail(childId),
    enabled: !isNaN(childId),
  });
  const classLevel = child?.child.class_level;
  const { data: syl } = useQuery({
    queryKey: ["syllabus", classLevel],
    queryFn: () => api.syllabus(classLevel!),
    enabled: classLevel !== undefined,
  });
  const { data: topicStates } = useQuery({
    queryKey: ["topic-state", childId],
    queryFn: () => api.topicState(childId),
    enabled: !isNaN(childId),
  });

  // Index by (subject, topic) for O(1) lookup while rendering.
  const stateBy = useMemo(() => {
    const m = new Map<string, TopicStateRow>();
    for (const r of topicStates || []) m.set(`${r.subject}::${r.topic}`, r);
    return m;
  }, [topicStates]);

  const todayISO = useMemo(() => todayISOInIST(), []);

  if (!child || !syl) {
    return (
      <div>
        <ChildHeader title="Syllabus" />
        <div className="space-y-4" aria-hidden="true">
          <div className="surface p-4 space-y-3">
            <div className="skeleton h-4 w-40" />
            <div className="skeleton h-3 w-full" />
            <div className="skeleton h-3 w-5/6" />
          </div>
          <div className="surface p-4 space-y-3">
            <div className="skeleton h-4 w-44" />
            <div className="skeleton h-3 w-full" />
            <div className="skeleton h-3 w-2/3" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <ChildHeader title="Syllabus" />
      <div className="text-sm text-gray-500 mb-3">
        Class {classLevel}, school year {syl.school_year || "?"} ·
        <Link to="/settings/syllabus" className="ml-2 text-blue-700 hover:underline">Calibrate cycles →</Link>
      </div>

      <div className="space-y-4">
        {syl.cycles.map((c) => {
          const isCurrent = c.start <= todayISO && todayISO <= c.end;
          return (
            <section key={c.name} className={`bg-white border rounded shadow-sm p-4 ${isCurrent ? "border-purple-400" : "border-gray-200"}`}>
              <div className="flex items-baseline justify-between">
                <h3 className="font-semibold">
                  {c.name}
                  {isCurrent && <span className="ml-2 text-xs text-purple-700 bg-purple-50 border border-purple-200 rounded px-2 py-0.5">Current</span>}
                  {c.overridden && <span className="ml-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">Overridden</span>}
                </h3>
                <div className="text-sm text-gray-600">{c.start} → {c.end}</div>
              </div>
              {c.override_note && (
                <div className="text-xs text-amber-700 mt-1">Note: {c.override_note}</div>
              )}
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                {Object.entries(c.topics_by_subject || {}).map(([subj, topics]) => (
                  <div key={subj} className="text-sm">
                    <div className="font-medium text-gray-800 mb-1 flex items-center">
                      <span>{subj}</span>
                      <LanguageChip subject={subj} />
                    </div>
                    <ul className="space-y-0.5 text-gray-700">
                      {topics.map((t) => {
                        const st = c.topic_status?.[subj]?.[t]?.status;
                        // Topic state lookup. Topics are stored in the
                        // syllabus as e.g. "LC1: Snake Trouble..." — that's
                        // also the format `fuzzy_topic_for` returns, so the
                        // keys line up.
                        const ms = stateBy.get(`${subj}::${t}`);
                        return (
                          <li key={t} className="flex items-center gap-2">
                            <span className="w-4 text-xs">
                              {st === "covered" ? "✅" :
                                st === "skipped" ? "⏭️" :
                                  st === "delayed" ? "⏳" :
                                    st === "in_progress" ? "🟡" : "·"}
                            </span>
                            {ms ? <MasteryDot row={ms} /> : <span style={{ width: 10 }} aria-hidden />}
                            <span>{t}</span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
