/**
 * CycleView — Tab 2 of the Syllabus redesign. The "this week" focus.
 *
 * Three sections:
 *   1. Cycle progress bar — Day X of N, percentage, end date
 *   2. This week's topics — proportional position in the cycle, picks
 *      topics in the active band (covered + in_progress + delayed)
 *   3. Decaying list — the actionable callout. Top-N decayed topics
 *      across all subjects, with last graded percent + age.
 *   4. Coverage progress per subject — calibration vs the school's plan.
 *
 * Built around the *current* cycle. If there is none (off-cycle, e.g.
 * mid-summer), shows a "not in a cycle right now" empty state with a
 * link to switch to the Subjects tab.
 */
import { useMemo } from "react";
import {
  SyllabusCycleFull,
  SyllabusDoc,
  TopicStateRow,
} from "../../api";
import { MasteryPelletFromRow, CoverageStatus } from "../MasteryPellet";
import { langOf, SyllabusFilterState, filterTopic } from "../SyllabusFilters";

type Props = {
  syllabus: SyllabusDoc;
  states: TopicStateRow[];
  todayISO: string;
  filters: SyllabusFilterState;
  onTopicClick: (subject: string, topic: string) => void;
  onSwitchTab: (tab: "subjects" | "cycle" | "list") => void;
  isSubjectHidden: (subject: string) => boolean;
};

function daysBetween(a: string, b: string): number {
  const ta = new Date(a + "T00:00:00").getTime();
  const tb = new Date(b + "T00:00:00").getTime();
  return Math.round((tb - ta) / (24 * 60 * 60 * 1000));
}

function topicsForThisWeek(
  cycle: SyllabusCycleFull,
  _todayISO: string,
): Array<{ subject: string; topic: string }> {
  // Heuristic: surfaces topics whose coverage status is "in_progress",
  // plus any "delayed" (overdue from earlier). Falls back to the next
  // 2-3 uncovered topics if nothing's marked.
  const out: Array<{ subject: string; topic: string }> = [];
  const subjects = Object.keys(cycle.topics_by_subject || {});

  for (const subj of subjects) {
    const topics = cycle.topics_by_subject[subj] || [];
    const ts = cycle.topic_status?.[subj] || {};
    for (const t of topics) {
      const st = ts[t]?.status;
      if (st === "in_progress" || st === "delayed") {
        out.push({ subject: subj, topic: t });
      }
    }
  }
  if (out.length > 0) return out;

  // Fallback — if no in-progress flags, show the first uncovered topic
  // per subject (best-effort guess at "what's next").
  for (const subj of subjects) {
    const topics = cycle.topics_by_subject[subj] || [];
    const ts = cycle.topic_status?.[subj] || {};
    const next = topics.find((t) => !ts[t]?.status || ts[t]?.status === null);
    if (next) out.push({ subject: subj, topic: next });
  }
  return out.slice(0, 6);
}

export function CycleView({
  syllabus,
  states,
  todayISO,
  filters,
  onTopicClick,
  onSwitchTab,
  isSubjectHidden,
}: Props) {
  const stateBy = useMemo(() => {
    const m = new Map<string, TopicStateRow>();
    for (const r of states) m.set(`${r.subject}::${r.topic}`, r);
    return m;
  }, [states]);

  const cycle = useMemo(
    () =>
      syllabus.cycles.find(
        (c) => c.start <= todayISO && todayISO <= c.end,
      ),
    [syllabus, todayISO],
  );

  if (!cycle) {
    return (
      <div className="surface p-6 text-center text-sm text-gray-600">
        Not currently inside any defined learning cycle.
        <div className="mt-2">
          <button
            type="button"
            className="text-blue-700 hover:underline"
            onClick={() => onSwitchTab("subjects")}
          >
            Open the subjects view →
          </button>
        </div>
      </div>
    );
  }

  const totalDays = daysBetween(cycle.start, cycle.end);
  const dayN = Math.max(0, daysBetween(cycle.start, todayISO));
  const daysLeft = Math.max(0, daysBetween(todayISO, cycle.end));
  const pct = totalDays > 0 ? Math.min(100, (dayN / totalDays) * 100) : 0;

  const thisWeek = topicsForThisWeek(cycle, todayISO).filter(
    (it) => !isSubjectHidden(it.subject),
  );

  // Decaying list — top-5 across all subjects, sorted by age × score.
  const decaying = useMemo(() => {
    return states
      .filter((r) => r.state === "decaying")
      .filter((r) => !isSubjectHidden(r.subject))
      .filter((r) =>
        filterTopic(filters, langOf, r.subject, r.state, null),
      )
      .sort((a, b) => {
        const ageA = a.last_assessed_at
          ? Math.abs(daysBetween(a.last_assessed_at, todayISO))
          : 0;
        const ageB = b.last_assessed_at
          ? Math.abs(daysBetween(b.last_assessed_at, todayISO))
          : 0;
        return ageB - ageA;
      })
      .slice(0, 5);
  }, [states, todayISO, filters, isSubjectHidden]);

  // Coverage progress per subject in the current cycle.
  const coverage = useMemo(() => {
    const out: Array<{
      subject: string;
      total: number;
      covered: number;
      in_progress: number;
      delayed: number;
      skipped: number;
      uncovered: number;
    }> = [];
    for (const [subj, topics] of Object.entries(cycle.topics_by_subject || {})) {
      if (isSubjectHidden(subj)) continue;
      const ts = cycle.topic_status?.[subj] || {};
      let covered = 0,
        inProgress = 0,
        delayed = 0,
        skipped = 0;
      for (const t of topics) {
        const st = ts[t]?.status;
        if (st === "covered") covered++;
        else if (st === "in_progress") inProgress++;
        else if (st === "delayed") delayed++;
        else if (st === "skipped") skipped++;
      }
      out.push({
        subject: subj,
        total: topics.length,
        covered,
        in_progress: inProgress,
        delayed,
        skipped,
        uncovered: topics.length - covered - inProgress - delayed - skipped,
      });
    }
    out.sort((a, b) => a.subject.localeCompare(b.subject));
    return out;
  }, [cycle, isSubjectHidden]);

  return (
    <div className="space-y-4">
      {/* §1 Cycle progress */}
      <section className="surface p-4">
        <div className="flex items-baseline justify-between mb-1">
          <span className="h-section text-purple-700">Current cycle</span>
          <span className="text-xs text-gray-500">
            {cycle.start} → {cycle.end}
          </span>
        </div>
        <div className="text-lg font-bold mb-1">{cycle.name}</div>
        <div className="text-sm text-gray-600 mb-2">
          Day <b>{dayN}</b> of {totalDays} · {daysLeft} days left
        </div>
        <div className="h-2 bg-gray-100 rounded overflow-hidden">
          <div
            className="h-full bg-purple-500/70"
            style={{ width: `${pct}%` }}
            aria-label={`${pct.toFixed(0)}% through cycle`}
          />
        </div>
      </section>

      {/* §2 This week's topics */}
      <section className="surface p-4">
        <div className="flex items-baseline justify-between mb-2">
          <span className="h-section text-blue-700">
            This week's topics
          </span>
          <span className="text-xs text-gray-400">
            from cycle topic_status (in_progress + delayed)
          </span>
        </div>
        {thisWeek.length === 0 ? (
          <div className="text-sm text-gray-500 italic">
            Nothing flagged in_progress or delayed for this cycle yet.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {thisWeek.map(({ subject, topic }) => {
              const ms = stateBy.get(`${subject}::${topic}`);
              const cov = (cycle.topic_status?.[subject]?.[topic]?.status ??
                null) as CoverageStatus;
              return (
                <li
                  key={`${subject}::${topic}`}
                  className="flex items-center gap-2 text-sm"
                >
                  <MasteryPelletFromRow row={ms} coverage={cov} />
                  <span className="text-xs uppercase tracking-wider text-gray-500 w-20 flex-shrink-0">
                    {subject}
                  </span>
                  <button
                    type="button"
                    onClick={() => onTopicClick(subject, topic)}
                    className="flex-1 text-left text-gray-800 hover:underline truncate"
                  >
                    {topic}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* §3 Decaying list */}
      <section className="surface p-4">
        <div className="flex items-baseline justify-between mb-2">
          <span className="h-section text-red-700">
            Decaying — needs a refresher
          </span>
          <span className="text-xs text-gray-400">{decaying.length} topic
            {decaying.length === 1 ? "" : "s"}
          </span>
        </div>
        {decaying.length === 0 ? (
          <div className="text-sm text-gray-500 italic">
            No decaying topics right now.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {decaying.map((r) => {
              const age = r.last_assessed_at
                ? Math.abs(daysBetween(r.last_assessed_at, todayISO))
                : null;
              return (
                <li
                  key={`${r.subject}::${r.topic}`}
                  className="flex items-center gap-2 text-sm"
                >
                  <MasteryPelletFromRow row={r} />
                  <span className="text-xs uppercase tracking-wider text-gray-500 w-20 flex-shrink-0">
                    {r.subject}
                  </span>
                  <button
                    type="button"
                    onClick={() => onTopicClick(r.subject, r.topic)}
                    className="flex-1 text-left text-gray-800 hover:underline truncate"
                  >
                    {r.topic}
                  </button>
                  <span className="text-xs text-gray-500 whitespace-nowrap">
                    {r.last_score != null && `${r.last_score.toFixed(0)}%`}
                    {age != null && ` · ${age}d ago`}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* §4 Coverage progress */}
      <section className="surface p-4">
        <div className="h-section text-gray-700 mb-2">Coverage progress</div>
        <div className="space-y-1.5 text-sm">
          {coverage.map((c) => (
            <div
              key={c.subject}
              className="flex items-center gap-2"
            >
              <span className="w-24 flex-shrink-0 text-gray-700 truncate">
                {c.subject}
              </span>
              <div className="flex-1 h-3 rounded overflow-hidden bg-gray-100 flex">
                {c.covered > 0 && (
                  <div
                    style={{ width: `${(c.covered / c.total) * 100}%` }}
                    title={`${c.covered} covered`}
                    className="bg-green-400/80"
                  />
                )}
                {c.in_progress > 0 && (
                  <div
                    style={{
                      width: `${(c.in_progress / c.total) * 100}%`,
                    }}
                    title={`${c.in_progress} in progress`}
                    className="bg-blue-400/80"
                  />
                )}
                {c.delayed > 0 && (
                  <div
                    style={{ width: `${(c.delayed / c.total) * 100}%` }}
                    title={`${c.delayed} delayed`}
                    className="bg-amber-400/80"
                  />
                )}
                {c.skipped > 0 && (
                  <div
                    style={{ width: `${(c.skipped / c.total) * 100}%` }}
                    title={`${c.skipped} skipped`}
                    className="bg-gray-400/80"
                  />
                )}
              </div>
              <span className="text-xs text-gray-500 w-20 text-right">
                {c.covered + c.in_progress}/{c.total}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
