/**
 * NotificationWhy — the (why?) popover on every Notifications-page row.
 *
 * Shows: rule_id, tier, the structured `why` payload (datapoints), and
 * a snooze action with three quick options:
 *   1 day · 1 week · cancel snooze (when one is already active)
 *
 * The plan called this out as the explainability surface for every
 * notification — every dispatch should be traceable to the rule that
 * fired and the data that fed it. We don't paraphrase or hide the
 * payload; just lay it out as small key/value rows.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  api,
  NotificationRow,
  NotificationSnooze,
} from "../api";

type Props = {
  row: NotificationRow;
  childId: number | null;
};

const TIER_TONE: Record<string, string> = {
  now:    "bg-red-50 text-red-800 border-red-200",
  today:  "bg-amber-50 text-amber-800 border-amber-200",
  weekly: "bg-blue-50 text-blue-800 border-blue-200",
};

function fmtKey(k: string): string {
  return k.replace(/_/g, " ");
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return v.length === 0 ? "—" : v.map(String).join(", ");
  return JSON.stringify(v);
}

export function NotificationWhy({ row, childId }: Props) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();

  const snoozes = useQuery<NotificationSnooze[]>({
    queryKey: ["notification-snoozes"],
    queryFn: () => api.listNotificationSnoozes(),
    enabled: open,
    staleTime: 30_000,
  });

  const activeSnooze = (snoozes.data ?? []).find(
    (s) =>
      s.rule_id === row.rule_id &&
      (s.child_id === childId || s.child_id === null),
  );

  const addSnooze = useMutation({
    mutationFn: (days: number) => {
      const until = new Date();
      until.setUTCDate(until.getUTCDate() + days);
      return api.addNotificationSnooze({
        rule_id: row.rule_id || "",
        child_id: childId,
        until: until.toISOString(),
        reason: `snoozed for ${days}d via (why?) popover`,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notification-snoozes"] });
    },
  });

  const cancelSnooze = useMutation({
    mutationFn: () =>
      activeSnooze
        ? api.deleteNotificationSnooze(activeSnooze.id)
        : Promise.resolve({ ok: false, id: 0 }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notification-snoozes"] });
    },
  });

  if (!row.rule_id) return null;

  const why = row.why ?? {};
  const entries = Object.entries(why).filter(
    ([, v]) =>
      v !== null && v !== undefined && (typeof v !== "string" || v !== ""),
  );

  return (
    <div className="relative inline-block">
      <button
        className="text-blue-700 hover:underline text-xs"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        (why?)
      </button>
      {open && (
        <>
          {/* click-outside backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute right-0 mt-1 z-50 w-80 surface p-3 shadow-lg border border-gray-200 text-xs">
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-gray-700">{row.rule_id}</span>
              {row.tier && (
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${
                    TIER_TONE[row.tier] ?? "border-gray-300 text-gray-700"
                  }`}
                >
                  tier · {row.tier}
                </span>
              )}
            </div>

            {entries.length === 0 ? (
              <div className="text-gray-500 italic">no datapoints recorded</div>
            ) : (
              <dl className="space-y-1">
                {entries.map(([k, v]) => (
                  <div key={k} className="grid grid-cols-3 gap-2">
                    <dt className="col-span-1 text-gray-500 truncate">
                      {fmtKey(k)}
                    </dt>
                    <dd className="col-span-2 text-gray-900 break-words">
                      {fmtVal(v)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}

            <div className="mt-3 pt-2 border-t border-gray-200">
              {activeSnooze ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-gray-600">
                    snoozed until{" "}
                    {new Date(activeSnooze.until).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                  <button
                    className="text-xs text-red-700 hover:underline"
                    disabled={cancelSnooze.isPending}
                    onClick={() => cancelSnooze.mutate()}
                  >
                    {cancelSnooze.isPending ? "…" : "cancel"}
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">snooze this rule:</span>
                  <button
                    className="text-blue-700 hover:underline"
                    disabled={addSnooze.isPending}
                    onClick={() => addSnooze.mutate(1)}
                  >
                    1 day
                  </button>
                  <button
                    className="text-blue-700 hover:underline"
                    disabled={addSnooze.isPending}
                    onClick={() => addSnooze.mutate(7)}
                  >
                    1 week
                  </button>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
