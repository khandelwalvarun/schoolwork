/**
 * DailyBriefCard — one-paragraph synthesis per kid for the Today page.
 *
 * Built on the shared Tray primitive — same chevron/count/summary
 * pattern as the other Today strips. Default-expanded when there's
 * actionable signal; default-collapsed on a quiet day so the page
 * stays calm.
 *
 * Backed by services/daily_brief.py (Claude-driven via the existing
 * claude_cli backend, cached for the day server-side). The "↻"
 * action lives in the Tray's right slot.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DailyBrief } from "../api";
import { Tray, trayLineClass } from "./Tray";

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
      <div className="mb-4 px-3 py-1.5 rounded border border-gray-200 bg-gray-50/40">
        <div className="skeleton h-3 w-1/3 rounded" />
      </div>
    );
  }
  if (!data || data.length === 0) return null;

  const anySignal = data.some((b) => b.has_signal);
  const kidCount = data.length;

  return (
    <Tray
      title="📝 Today's read"
      summary={
        anySignal
          ? `${kidCount} kid${kidCount === 1 ? "" : "s"} · click to expand`
          : "quiet day"
      }
      tone="purple"
      // Auto-expand when there's signal; collapse on a quiet day so
      // the page is shorter when nothing's pressing.
      defaultCollapsed={!anySignal}
      rightSlot={
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            refreshAll.mutate();
          }}
          disabled={refreshAll.isPending}
          className="text-meta text-purple-700 hover:underline disabled:opacity-50"
          title="Force a fresh synthesis (calls Claude)"
        >
          {refreshAll.isPending ? "refreshing…" : "↻ refresh"}
        </button>
      }
    >
      <ul className="space-y-1">
        {data.map((b) => (
          <li
            key={b.child_id}
            className={trayLineClass("purple") + " leading-snug"}
          >
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
    </Tray>
  );
}
