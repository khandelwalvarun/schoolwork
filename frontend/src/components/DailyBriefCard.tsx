/**
 * DailyBriefCard — one-paragraph synthesis per kid for the Today page.
 *
 * Backed by services/daily_brief.py (Claude-driven via the existing
 * claude_cli backend, cached for the day server-side). Shows a quiet
 * "nothing pressing today" state when the kid has no items in the
 * 48-hour window.
 *
 * A small "↻" link lets the parent force a refresh — useful if a sync
 * just landed and they want the latest synthesis without waiting for
 * the cache to invalidate.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DailyBrief } from "../api";

export function DailyBriefCard() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<DailyBrief[]>({
    queryKey: ["daily-brief"],
    queryFn: () => api.dailyBrief() as Promise<DailyBrief[]>,
    staleTime: 5 * 60_000,
  });

  const refreshAll = useMutation({
    mutationFn: async () => {
      // hit /api/daily-brief?refresh=true (no child_id) — server-side
      // invalidate then rebuild for both kids.
      await fetch(`/api/daily-brief?refresh=true`);
      await qc.invalidateQueries({ queryKey: ["daily-brief"] });
    },
  });

  if (isLoading) {
    return (
      <section className="surface mb-4 p-4">
        <div className="skeleton h-3 w-1/2 rounded mb-2" />
        <div className="skeleton h-3 w-3/4 rounded" />
      </section>
    );
  }
  if (!data || data.length === 0) return null;

  const anySignal = data.some((b) => b.has_signal);

  return (
    <section className="surface mb-4 p-4">
      <div className="flex items-baseline justify-between mb-1">
        <span className="h-section text-purple-700">
          Today's read
          {!anySignal && <span className="ml-2 text-gray-400 normal-case font-normal">· quiet day</span>}
        </span>
        <button
          type="button"
          onClick={() => refreshAll.mutate()}
          disabled={refreshAll.isPending}
          className="text-xs text-gray-500 hover:text-gray-800 disabled:opacity-50"
          title="Force a fresh synthesis (calls Claude)"
        >
          {refreshAll.isPending ? "refreshing…" : "↻ refresh"}
        </button>
      </div>
      <ul className="space-y-1.5">
        {data.map((b) => (
          <li key={b.child_id} className="text-sm leading-snug">
            <span className="font-semibold text-gray-700 mr-1">
              {b.child_name}:
            </span>
            <span
              className={
                b.has_signal ? "text-gray-900" : "text-gray-500 italic"
              }
            >
              {b.summary}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
