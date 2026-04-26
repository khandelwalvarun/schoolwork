/**
 * PatternsCard — the quiet, never-pushed surface for behavioural-pattern
 * flags (lateness / repeated-attempt / weekend-cramming).
 *
 * Per the pedagogy research synthesis, these are easy to weaponise into
 * "you're failing as a parent" / "your kid is failing" framings — so the
 * card stays passive: no badges in the nav, no notifications, no red
 * "alert" tone. It shows the 6 most recent months as a row of dots, one
 * row per flag. A dot is *filled* when the month tripped that flag, with
 * a tooltip explaining the count and a sample of titles.
 *
 * If no month tripped any flag, the card collapses to a single "no
 * patterns flagged this period" line so it doesn't waste space.
 */
import { useQuery } from "@tanstack/react-query";
import { api, PatternMonth } from "../api";

type FlagKey = "lateness" | "repeated_attempt" | "weekend_cramming";

const FLAG_META: Record<
  FlagKey,
  { label: string; tone: string; description: string }
> = {
  lateness: {
    label: "Lateness",
    tone: "oklch(60% 0.18 28)",
    description:
      "Three or more assignments in the month flagged as 'likely missing' " +
      "(past-due + still 'assigned' for over a week, or marked late by school).",
  },
  repeated_attempt: {
    label: "Repeated attempts",
    tone: "oklch(60% 0.16 65)",
    description:
      "Same topic graded ≥ 3 times in the month — the school is reteaching, " +
      "which can mean the kid hasn't yet held it.",
  },
  weekend_cramming: {
    label: "Weekend cramming",
    tone: "oklch(48% 0.20 290)",
    description:
      "≥ 60 % of parent-marked submissions in the month land on Saturday or " +
      "Sunday (with at least 5 events). Suggests work is bunched up.",
  },
};

function fmtMonth(m: string): string {
  const [y, mm] = m.split("-").map((s) => parseInt(s, 10));
  const d = new Date(Date.UTC(y, mm - 1, 1));
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

function tooltipFor(flag: FlagKey, m: PatternMonth): string {
  if (flag === "lateness") {
    const d = m.detail.lateness;
    if (!m.lateness) return `${d.count}/${d.threshold} below threshold`;
    return (
      `${fmtMonth(m.month)} · ${d.count} late items\n` +
      (d.examples.length ? `e.g. ${d.examples.join("; ")}` : "")
    );
  }
  if (flag === "repeated_attempt") {
    const d = m.detail.repeated_attempt;
    if (!m.repeated_attempt) return `no topic ≥ ${d.threshold} attempts`;
    return (
      `${fmtMonth(m.month)} · reteach detected\n` +
      d.topics
        .map((t) => `${t.subject}/${t.topic} ×${t.count}`)
        .join("\n")
    );
  }
  // weekend_cramming
  const d = m.detail.weekend_cramming;
  if (d.note) return d.note;
  if (!m.weekend_cramming) {
    return `${d.weekend}/${d.total} on weekends — under ${Math.round(
      d.fraction_threshold * 100,
    )}% threshold`;
  }
  return (
    `${fmtMonth(m.month)} · ${d.weekend}/${d.total} on weekends\n` +
    (d.examples?.length ? `e.g. ${d.examples.join("; ")}` : "")
  );
}

export function PatternsCard({ childId }: { childId: number }) {
  const { data, isLoading } = useQuery<PatternMonth[]>({
    queryKey: ["patterns", childId],
    queryFn: () => api.patterns(childId),
    staleTime: 60_000,
  });

  if (isLoading || !data) {
    return (
      <div className="surface p-4">
        <div className="h-section text-gray-700 mb-2">Patterns · last 6 months</div>
        <div className="h-12 skeleton rounded" />
      </div>
    );
  }
  // Show oldest → newest left-to-right.
  const months = [...data].reverse();
  const anyTripped = months.some(
    (m) => m.lateness || m.repeated_attempt || m.weekend_cramming,
  );

  return (
    <div className="surface p-4">
      <div className="flex items-baseline justify-between mb-1">
        <span className="h-section text-gray-700">Patterns · last 6 months</span>
        <span className="text-xs text-gray-400">
          quiet signals · never push
        </span>
      </div>
      {!anyTripped ? (
        <div className="text-sm text-gray-500 italic mt-2">
          No patterns flagged this period.
        </div>
      ) : (
        <div className="mt-2 space-y-1.5">
          {(Object.keys(FLAG_META) as FlagKey[]).map((flag) => {
            const meta = FLAG_META[flag];
            const tripped = months.some((m) => m[flag]);
            return (
              <div
                key={flag}
                className="flex items-center gap-3 text-sm"
              >
                <span
                  className="w-32 flex-shrink-0 text-gray-700"
                  title={meta.description}
                >
                  {meta.label}
                </span>
                <div className="flex items-center gap-1">
                  {months.map((m) => {
                    const on = m[flag];
                    return (
                      <span
                        key={m.month}
                        title={tooltipFor(flag, m)}
                        className="inline-flex flex-col items-center"
                        style={{ width: 28 }}
                      >
                        <span
                          className="block rounded-full"
                          style={{
                            width: 12,
                            height: 12,
                            backgroundColor: on
                              ? meta.tone
                              : "oklch(92% 0.005 250)",
                            border: on
                              ? "none"
                              : "1px solid oklch(85% 0.01 250)",
                          }}
                        />
                        <span
                          className="text-[9px] text-gray-400 mt-0.5"
                          aria-hidden
                        >
                          {fmtMonth(m.month).split(" ")[0]}
                        </span>
                      </span>
                    );
                  })}
                </div>
                {!tripped && (
                  <span className="text-[11px] text-gray-400 italic ml-2">
                    not triggered
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
      <p className="text-[11px] text-gray-500 mt-3 leading-snug">
        These are signals from incomplete data, never verdicts. They
        sit here as a passive reference — read them, don't moralize them.
      </p>
    </div>
  );
}
