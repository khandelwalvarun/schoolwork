/**
 * Mindspark — narrow performance-metrics view per kid.
 *
 * Shows what we've already scraped (cached in mindspark_session +
 * mindspark_topic_progress); doesn't trigger a new scrape on render.
 * The "Sync now" button kicks one off — slow path, takes a couple of
 * minutes thanks to the rate limiter inside the scraper.
 *
 * Two sections per kid:
 *   - Topics: table of subject/topic/accuracy/attempts/mastery, sorted
 *     by accuracy ascending so weak topics float to top.
 *   - Recent sessions: last 20, ordered by started_at desc.
 *
 * Empty states explain whether (a) Mindspark is disabled in env,
 * (b) credentials aren't configured for this kid, or (c) we haven't
 * scraped yet — different problems, different fixes.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Button } from "../components/Button";
import { Tray, trayLineClass } from "../components/Tray";

type Topic = {
  id: number;
  subject: string;
  topic_name: string;
  accuracy_pct: number | null;
  questions_attempted: number | null;
  time_spent_sec: number | null;
  mastery_level: string | null;
  last_activity_at: string | null;
  updated_at: string | null;
};
type Session = {
  id: number;
  external_id: string;
  subject: string | null;
  topic_name: string | null;
  started_at: string | null;
  duration_sec: number | null;
  questions_total: number | null;
  questions_correct: number | null;
  accuracy_pct: number | null;
};
type Kid = {
  child_id: number;
  child_name: string;
  topics: Topic[];
  sessions: Session[];
};

function fmtMin(secs: number | null): string {
  if (secs == null) return "—";
  if (secs < 60) return `${secs}s`;
  return `${Math.round(secs / 60)} min`;
}
function fmtPct(p: number | null): string {
  if (p == null) return "—";
  return `${p.toFixed(0)}%`;
}
function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const MASTERY_TONE: Record<string, string> = {
  beginner:  "border-gray-300 text-gray-700 bg-gray-50",
  familiar:  "border-amber-300 text-amber-800 bg-amber-50",
  proficient:"border-blue-300 text-blue-800 bg-blue-50",
  mastered:  "border-green-300 text-green-800 bg-green-50",
  advanced:  "border-purple-300 text-purple-800 bg-purple-50",
};

export default function Mindspark() {
  const qc = useQueryClient();
  const [busyKid, setBusyKid] = useState<number | null>(null);

  const { data, isLoading } = useQuery<{ kids: Kid[] }>({
    queryKey: ["mindspark-progress"],
    queryFn: () => api.mindsparkProgress(),
    staleTime: 60_000,
  });

  const sync = useMutation({
    mutationFn: (childId?: number) => api.mindsparkSync(childId),
    onMutate: (childId) => setBusyKid(childId ?? -1),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mindspark-progress"] }),
    onSettled: () => setBusyKid(null),
  });

  const kids = data?.kids ?? [];

  return (
    <div className="pb-12">
      <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
        <h2 className="text-2xl font-bold">Mindspark</h2>
        <Button
          size="sm"
          variant="primary"
          onClick={() => sync.mutate(undefined)}
          disabled={busyKid !== null}
          loading={busyKid === -1}
          title="Trigger a metrics scrape now (slow — ~2 minutes per kid)"
        >
          {busyKid === -1 ? "Syncing all…" : "Sync all kids"}
        </Button>
      </div>
      <p className="text-sm text-gray-600 mb-6">
        Performance metrics only — score, regularity, weak topics. The full
        questions stay inside Mindspark; we just track how the kid is doing.
        Slow-rate scraper, runs nightly at 03:30 IST.
      </p>

      {isLoading && <div className="text-gray-400">Loading…</div>}

      {!isLoading && kids.length === 0 && (
        <div className="surface p-6 text-center text-sm text-gray-500">
          No data yet. Set <code>MINDSPARK_ENABLED=true</code> in .env plus
          <code> MINDSPARK_USERNAME_&lt;child_id&gt;</code> +{" "}
          <code>MINDSPARK_PASSWORD_&lt;child_id&gt;</code>, then click "Sync all
          kids" above.
        </div>
      )}

      <div className="space-y-8">
        {kids.map((kid) => (
          <KidSection
            key={kid.child_id}
            kid={kid}
            onSync={() => sync.mutate(kid.child_id)}
            busy={busyKid === kid.child_id}
          />
        ))}
      </div>
    </div>
  );
}

function KidSection({
  kid,
  onSync,
  busy,
}: {
  kid: Kid;
  onSync: () => void;
  busy: boolean;
}) {
  const topicsByAccuracy = useMemo(
    () =>
      [...kid.topics].sort((a, b) => {
        const av = a.accuracy_pct ?? 100;
        const bv = b.accuracy_pct ?? 100;
        return av - bv;
      }),
    [kid.topics],
  );

  const totals = useMemo(() => {
    const sessions = kid.sessions;
    let total = 0;
    let correct = 0;
    let secs = 0;
    for (const s of sessions) {
      total += s.questions_total ?? 0;
      correct += s.questions_correct ?? 0;
      secs += s.duration_sec ?? 0;
    }
    const acc = total > 0 ? (correct * 100) / total : null;
    return {
      session_count: sessions.length,
      questions: total,
      accuracy_pct: acc,
      time_min: Math.round(secs / 60),
    };
  }, [kid.sessions]);

  // Show top 3 weakest topics by default; the rest hide behind the
  // tray's collapse. Keeps the page scannable when a kid has 30+
  // tracked topics. Bottom-up sort means concerns surface first.
  const weakestThree = topicsByAccuracy.slice(0, 3);
  const recentSessions = kid.sessions.slice(0, 5);

  return (
    <section className="mb-8 pt-5 border-t border-[color:var(--line)]">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-lede font-bold">{kid.child_name}</h3>
        <Button
          size="sm"
          variant="ghost"
          onClick={onSync}
          disabled={busy}
          loading={busy}
        >
          {busy ? "syncing…" : "sync this kid"}
        </Button>
      </div>

      {/* One-line stats strip — number-first, no giant text. */}
      <div className="flex items-baseline gap-x-5 gap-y-1 text-body flex-wrap mb-3">
        <span>
          <span className="font-semibold text-gray-900 tabular-nums">{totals.session_count}</span>
          <span className="text-gray-500 ml-1">sessions</span>
        </span>
        <span>
          <span className="font-semibold text-gray-900 tabular-nums">{totals.questions}</span>
          <span className="text-gray-500 ml-1">questions</span>
        </span>
        <span>
          <span
            className={
              "font-semibold tabular-nums " +
              (totals.accuracy_pct != null && totals.accuracy_pct < 70
                ? "text-red-700"
                : "text-emerald-700")
            }
          >
            {fmtPct(totals.accuracy_pct)}
          </span>
          <span className="text-gray-500 ml-1">accuracy</span>
        </span>
        <span>
          <span className="font-semibold text-gray-900 tabular-nums">{totals.time_min}</span>
          <span className="text-gray-500 ml-1">min</span>
        </span>
      </div>

      {/* Weakest topics — auto-shows top 3, expand for more. */}
      {topicsByAccuracy.length > 0 && (
        <Tray
          title="🎯 Weakest topics"
          count={topicsByAccuracy.length}
          summary={
            topicsByAccuracy.length > weakestThree.length
              ? `showing weakest ${weakestThree.length}`
              : undefined
          }
          tone="amber"
          defaultCollapsed={false}
        >
          <ul className="space-y-0.5">
            {(topicsByAccuracy.length > 3 ? topicsByAccuracy : weakestThree).map((t) => (
              <li key={t.id} className={trayLineClass("amber") + " flex items-baseline gap-2"}>
                <span className="text-meta uppercase tracking-wider text-gray-500 shrink-0 w-20 truncate">
                  {t.subject}
                </span>
                <span className="flex-1 truncate text-body">{t.topic_name}</span>
                {t.mastery_level && (
                  <span
                    className={`inline-flex items-center px-1.5 py-0 rounded text-meta border ${
                      MASTERY_TONE[t.mastery_level] || "border-gray-200 bg-gray-50 text-gray-700"
                    }`}
                  >
                    {t.mastery_level}
                  </span>
                )}
                <span className="text-meta text-gray-500 whitespace-nowrap tabular-nums">
                  {fmtPct(t.accuracy_pct)}
                  {t.questions_attempted != null && (
                    <span className="text-gray-400"> · {t.questions_attempted}q</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </Tray>
      )}

      {/* Recent sessions — collapsed by default; the totals strip
          above already gives the gestalt. Open if you want to look
          at individual practice runs. */}
      {kid.sessions.length > 0 && (
        <Tray
          title="🕒 Recent sessions"
          count={kid.sessions.length}
          summary={kid.sessions.length > 5 ? "first 5 shown" : undefined}
          tone="gray"
          defaultCollapsed
        >
          <ul className="space-y-0.5">
            {recentSessions.map((s) => (
              <li key={s.id} className={trayLineClass("gray") + " flex items-baseline gap-2"}>
                <span className="text-meta text-gray-500 shrink-0 w-12">
                  {fmtDate(s.started_at)}
                </span>
                {s.subject && (
                  <span className="text-meta uppercase tracking-wider text-gray-500 shrink-0 w-20 truncate">
                    {s.subject}
                  </span>
                )}
                <span className="flex-1 truncate text-body text-gray-800">
                  {s.topic_name || "(general)"}
                </span>
                <span className="text-meta text-gray-500 whitespace-nowrap tabular-nums">
                  {s.questions_correct ?? "?"}/{s.questions_total ?? "?"} · {fmtPct(s.accuracy_pct)} · {fmtMin(s.duration_sec)}
                </span>
              </li>
            ))}
          </ul>
        </Tray>
      )}

      {topicsByAccuracy.length === 0 && kid.sessions.length === 0 && (
        <div className="text-meta text-gray-500 italic">
          No data yet — run a sync.
        </div>
      )}
    </section>
  );
}
