/**
 * MindsparkPendingTray — surfaces weak / decaying Mindspark topics
 * as practice todos in each kid's section on Today.
 *
 * Why this lives here: the user thinks of "what my kid still needs to
 * do" as a single concern, not split across "school assignments" and
 * "Mindspark practice". Burying Mindspark behind its own page meant
 * pending practice fell off the parent's radar. This tray puts a
 * scannable list in front of the bucket section, in the same Tray
 * vocabulary as everything else on Today.
 *
 * "Pending" rule (cheap heuristic, tuned to be NOT noisy):
 *   - accuracy_pct < 70%               → weak topic, needs practice
 *   - OR mastery_level == 'beginner'   → just started, keep going
 *   - OR last_activity_at older than 14 days  → mastery decay
 *
 * Topics that satisfy ANY of those, sorted by accuracy ascending so
 * the most concerning shows first. Capped at 6 visible rows; the
 * rest are accessible from /mindspark via an "all" link.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Tray, trayLineClass } from "./Tray";

type Topic = {
  id: number;
  subject: string;
  topic_name: string;
  accuracy_pct: number | null;
  questions_attempted: number | null;
  mastery_level: string | null;
  last_activity_at: string | null;
};

const STALE_DAYS = 14;
const ACCURACY_FLOOR = 70;
const MASTERY_PENDING = new Set(["beginner", "familiar"]);
const VISIBLE_CAP = 6;

function isStale(iso: string | null): boolean {
  if (!iso) return true; // never seen → definitely pending
  const d = Date.parse(iso);
  if (isNaN(d)) return true;
  const ageDays = (Date.now() - d) / (24 * 60 * 60 * 1000);
  return ageDays > STALE_DAYS;
}

/** Returns true when the topic is "pending" — the row should appear. */
function isPending(t: Topic): boolean {
  if (t.accuracy_pct != null && t.accuracy_pct < ACCURACY_FLOOR) return true;
  if (t.mastery_level && MASTERY_PENDING.has(t.mastery_level)) return true;
  if (isStale(t.last_activity_at)) return true;
  return false;
}

/** A short non-numeric reason label — the accuracy % is shown as
 *  its own chip, so this only carries the qualitative reason
 *  (mastery level, staleness). Avoids the "0% · 0%" duplication
 *  that would result from echoing the accuracy here too. */
function pendingTag(t: Topic): string | null {
  if (t.mastery_level && MASTERY_PENDING.has(t.mastery_level)) {
    return t.mastery_level;
  }
  if (isStale(t.last_activity_at)) return "stale";
  return null; // weak-accuracy alone — chip already says it
}

export function MindsparkPendingTray({ childId }: { childId: number }) {
  // Reuse the cockpit-wide mindspark progress query; same key as the
  // /mindspark page so cache is shared.
  const { data, isLoading } = useQuery({
    queryKey: ["mindspark-progress"],
    queryFn: () => api.mindsparkProgress(),
    staleTime: 60_000,
  });

  const pending: Topic[] = useMemo(() => {
    const kid = data?.kids?.find((k) => k.child_id === childId);
    if (!kid) return [];
    return [...kid.topics]
      .filter(isPending)
      .sort((a, b) => {
        const av = a.accuracy_pct ?? 100;
        const bv = b.accuracy_pct ?? 100;
        return av - bv;
      });
  }, [data, childId]);

  if (isLoading) return null;
  if (pending.length === 0) return null;

  const visible = pending.slice(0, VISIBLE_CAP);
  const hidden = pending.length - visible.length;

  return (
    <Tray
      title="🎯 Mindspark — pending practice"
      count={pending.length}
      summary={
        hidden > 0
          ? `showing weakest ${visible.length} · ${hidden} more`
          : "weakest first"
      }
      tone="amber"
      // Auto-expand when the count is small (parent wants to see at
      // a glance); collapse when there's a long tail so the kid
      // section doesn't get dominated by a 20-row practice list.
      defaultCollapsed={pending.length > 4}
      rightSlot={
        <Link
          to="/mindspark"
          onClick={(e) => e.stopPropagation()}
          className="text-meta text-amber-700 hover:underline"
        >
          all topics →
        </Link>
      }
    >
      <ul className="space-y-0.5">
        {visible.map((t) => {
          const tag = pendingTag(t);
          return (
            <li key={t.id} className={trayLineClass("amber") + " flex items-baseline gap-2"}>
              <span className="text-meta uppercase tracking-wider text-gray-500 shrink-0 w-28 truncate" title={t.subject}>
                {t.subject}
              </span>
              <span className="flex-1 truncate text-body" title={t.topic_name}>
                {t.topic_name}
              </span>
              {t.questions_attempted != null && (
                <span className="text-meta text-gray-400 tabular-nums whitespace-nowrap">
                  {t.questions_attempted}q
                </span>
              )}
              {t.accuracy_pct != null && (
                <span
                  className={
                    "tabular-nums text-meta font-semibold w-10 text-right " +
                    (t.accuracy_pct < ACCURACY_FLOOR
                      ? "text-red-700"
                      : "text-gray-700")
                  }
                >
                  {t.accuracy_pct.toFixed(0)}%
                </span>
              )}
              {tag && (
                <span className="chip-amber text-meta">{tag}</span>
              )}
            </li>
          );
        })}
      </ul>
    </Tray>
  );
}
