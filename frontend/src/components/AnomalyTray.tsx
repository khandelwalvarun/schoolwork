/**
 * AnomalyTray — compact strip on Today flagging off-trend grades.
 *
 * Built on the shared Tray primitive. Each row has a clear "Dismiss"
 * button on the right (used to be a tiny "✓ ack" link); the tray
 * also exposes a "Dismiss all" action in the right slot when more
 * than one is open, so the parent can clear the whole strip in one
 * click after a quick scan.
 *
 * Dismissals are persistent (server-side `anomaly_status='dismissed'`)
 * — once acknowledged the row stays gone across reloads. Use the
 * GradeAnomalyCard inside the audit drawer to undo.
 */
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, AnomalyStatus } from "../api";
import { Tray, trayLineClass } from "./Tray";

type AnomalyRow = {
  grade_id: number;
  child_id?: number;
  child_name?: string;
  subject: string;
  graded_date: string;
  pct: number;
  reason: string;
  title?: string | null;
  explanation?: string | null;
  status?: AnomalyStatus | null;
  status_at?: string | null;
};

export function AnomalyTray() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<AnomalyRow[]>({
    queryKey: ["anomalies"],
    queryFn: () => api.gradeAnomalies(),
    staleTime: 60_000,
  });

  // Bulk-dismiss: hit the per-grade endpoint for every open row in
  // parallel. Works fine for 8-10 anomalies; if this ever has 100+
  // rows we'd add a bulk endpoint.
  const dismissAll = useMutation({
    mutationFn: async (ids: number[]) => {
      await Promise.all(ids.map((id) => api.setAnomalyStatus(id, "dismissed")));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["anomalies"] }),
  });

  if (isLoading) return null;
  const allRows = data ?? [];
  const openRows = allRows.filter((r) => r.status !== "dismissed");
  if (openRows.length === 0) return null;

  const onChanged = () => qc.invalidateQueries({ queryKey: ["anomalies"] });

  return (
    <Tray
      title="🔴 Off-trend grades"
      count={openRows.length}
      summary={openRows.length === 1 ? "click to see why" : "review or dismiss"}
      tone="red"
      rightSlot={
        openRows.length > 1 ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (
                confirm(
                  `Dismiss all ${openRows.length} off-trend flags? You can still undo each one from the audit drawer.`,
                )
              ) {
                dismissAll.mutate(openRows.map((r) => r.grade_id));
              }
            }}
            disabled={dismissAll.isPending}
            className="text-meta text-red-700 hover:underline disabled:opacity-50"
            title="Mark all open flags as dismissed"
          >
            ✕ dismiss all
          </button>
        ) : null
      }
    >
      <ul className="space-y-0.5">
        {openRows.map((r) => (
          <AnomalyLine key={r.grade_id} r={r} onChanged={onChanged} />
        ))}
      </ul>
    </Tray>
  );
}

function AnomalyLine({
  r,
  onChanged,
}: {
  r: AnomalyRow;
  onChanged: () => void;
}) {
  const [showWhy, setShowWhy] = useState(false);
  const dismiss = useMutation({
    mutationFn: () => api.setAnomalyStatus(r.grade_id, "dismissed"),
    onSuccess: () => onChanged(),
  });

  const pctCls = r.pct < 70 ? "text-red-700 font-semibold" : "text-gray-800";

  return (
    <li className={trayLineClass("red")}>
      <div className="flex items-baseline gap-2 flex-wrap">
        {r.child_name && (
          <Link
            to={`/child/${r.child_id}/grades`}
            className="font-medium text-gray-900 hover:text-blue-700"
          >
            {r.child_name}
          </Link>
        )}
        <span className="text-gray-700">{r.subject}</span>
        <span className={pctCls}>{r.pct.toFixed(0)}%</span>
        <span className="text-meta text-gray-500">· {r.graded_date}</span>
        {r.title && (
          <span className="text-meta text-gray-500 truncate max-w-xs" title={r.title}>
            — {r.title}
          </span>
        )}
        {r.explanation && (
          <button
            type="button"
            onClick={() => setShowWhy((x) => !x)}
            className="text-meta text-blue-700 hover:underline"
          >
            {showWhy ? "hide" : "why?"}
          </button>
        )}
        {/* Dismiss button — clearly labelled, with a real
            chip-style affordance instead of the prior tiny gray
            "✓ ack" link. The parent should be able to clear a flag
            without hunting for it. */}
        <button
          type="button"
          onClick={() => dismiss.mutate()}
          disabled={dismiss.isPending}
          className="ml-auto chip-gray hover:bg-gray-200 disabled:opacity-50"
          title="Dismiss — mark this flag as reviewed and hide"
        >
          ✕ dismiss
        </button>
      </div>
      {showWhy && r.explanation && (
        <div className="text-body text-gray-700 mt-1 mb-1 leading-snug">
          {r.explanation}
        </div>
      )}
    </li>
  );
}
