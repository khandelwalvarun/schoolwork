import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, NotificationEvent, ReplayResult } from "../api";
import { SkeletonList, Skeleton } from "../components/Skeleton";
import { NotificationWhy } from "../components/NotificationWhy";
import { formatDateTime } from "../util/dates";

const TIER_CHIP: Record<string, string> = {
  now:    "bg-red-50 text-red-800 border border-red-200",
  today:  "bg-amber-50 text-amber-800 border border-amber-200",
  weekly: "bg-blue-50 text-blue-800 border border-blue-200",
};

export default function Notifications() {
  const [sinceDays, setSinceDays] = useState(14);
  const { data, isLoading } = useQuery({
    queryKey: ["notifications", sinceDays],
    queryFn: () => api.notifications(sinceDays),
  });
  const [replay, setReplay] = useState<ReplayResult | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);

  const runReplay = async () => {
    setReplayLoading(true);
    try {
      const r = await api.replayNotifications(sinceDays);
      setReplay(r);
    } finally {
      setReplayLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div>
        <Skeleton w={200} h={28} className="mb-4" />
        <SkeletonList rows={8} />
      </div>
    );
  }
  const events = (data || []) as NotificationEvent[];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Notifications</h2>
        <div className="flex gap-2 items-center text-sm">
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={sinceDays}
            onChange={(e) => setSinceDays(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
          </select>
          <button
            className="bg-gray-700 text-white text-sm rounded px-3 py-1 hover:bg-gray-800 disabled:opacity-50"
            disabled={replayLoading}
            onClick={runReplay}
          >
            {replayLoading ? "Replaying…" : "Replay under current policy"}
          </button>
        </div>
      </div>

      {replay && (
        <section className="bg-amber-50 border border-amber-200 rounded p-4 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <b>Counterfactual replay</b> — last {replay.summary.since_days ?? sinceDays} days
            </div>
            <button
              className="text-xs text-gray-600 hover:text-gray-900"
              onClick={() => setReplay(null)}
            >dismiss</button>
          </div>
          <div className="text-sm text-gray-700 mt-1">
            Current policy would have: sent <b>{replay.summary.would_send}</b>, suppressed <b>{replay.summary.would_suppress}</b>.
            {replay.summary.changed > 0 && <> {replay.summary.changed} would change vs actual.</>}
          </div>
          <details className="mt-2">
            <summary className="text-xs text-gray-600 cursor-pointer select-none">Show per-event verdicts</summary>
            <table className="w-full text-xs mt-2">
              <thead>
                <tr className="text-left text-gray-500">
                  <th className="py-1 pr-3">Kind</th>
                  <th className="py-1 pr-3">Notability</th>
                  {Object.keys(replay.events[0]?.channels || {}).map((c) => (
                    <th key={c} className="py-1 pr-3">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {replay.events.map((e) => (
                  <tr key={e.event_id} className="border-t border-amber-200">
                    <td className="py-1 pr-3 font-mono">{e.kind}</td>
                    <td className="py-1 pr-3">{e.notability.toFixed(2)}</td>
                    {Object.entries(e.channels).map(([cname, v]) => (
                      <td key={cname} className="py-1 pr-3">
                        <span className={v.replay_status === "sent" ? "text-green-700" : "text-gray-600"}>
                          {v.replay_status}
                        </span>
                        {v.changed && <span className="ml-1 text-red-700">△</span>}
                        {v.replay_reason && (
                          <span className="text-gray-400 ml-1">({v.replay_reason})</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>
      )}

      <table className="w-full text-sm bg-white border border-gray-200 rounded shadow-sm">
        <thead>
          <tr className="text-left text-gray-500 text-xs uppercase border-b border-gray-100">
            <th className="py-2 px-3 font-medium">When</th>
            <th className="py-2 px-3 font-medium">Kind</th>
            <th className="py-2 px-3 font-medium">Tier</th>
            <th className="py-2 px-3 font-medium">Notability</th>
            <th className="py-2 px-3 font-medium">Child</th>
            <th className="py-2 px-3 font-medium">Subject</th>
            <th className="py-2 px-3 font-medium">Channels</th>
            <th className="py-2 px-3 font-medium">Why</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => {
            // Pick the most-informative row for the (why?) popover —
            // any 'sent' first, else any with a populated why payload.
            const whyRow =
              e.notifications.find((n) => n.status === "sent" && n.rule_id) ||
              e.notifications.find((n) => n.rule_id);
            const tier = whyRow?.tier;
            return (
              <tr key={e.id} className="border-t border-gray-100 hover:bg-gray-50 align-top">
                <td className="py-2 px-3 text-gray-500 whitespace-nowrap" title={e.created_at}>{formatDateTime(e.created_at)}</td>
                <td className="py-2 px-3 font-mono text-xs">{e.kind}</td>
                <td className="py-2 px-3">
                  {tier ? (
                    <span
                      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] ${
                        TIER_CHIP[tier] ?? "border border-gray-300 text-gray-700"
                      }`}
                    >
                      {tier}
                    </span>
                  ) : (
                    <span className="text-gray-400 text-xs">—</span>
                  )}
                </td>
                <td className="py-2 px-3">{e.notability.toFixed(2)}</td>
                <td className="py-2 px-3">{e.child_id ?? "—"}</td>
                <td className="py-2 px-3 text-gray-600">{e.subject}</td>
                <td className="py-2 px-3 space-x-2">
                  {e.notifications.map((n, i) => (
                    <span
                      key={i}
                      className={`chip-${n.status === "sent" ? "green" : n.status === "failed" ? "red" : "amber"}`}
                      title={n.error || ""}
                    >
                      {n.channel}: {n.status}
                    </span>
                  ))}
                </td>
                <td className="py-2 px-3">
                  {whyRow ? (
                    <NotificationWhy row={whyRow} childId={e.child_id} />
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
