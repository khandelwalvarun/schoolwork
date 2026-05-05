/**
 * GradeAnomalyCard — Claude-generated hypothesis when a grade landed
 * off the kid's subject trend.
 *
 * Detection is deterministic (services/anomaly.py: median + MAD with
 * min 2 peers). Hypotheses are pre-warmed nightly by the
 * anomaly_explainer job, so this card almost always renders cached
 * text instantly. If the cache is cold, it fetches on first open.
 *
 * Adds parent-acknowledgement actions: dismiss (clear the flag),
 * escalate (mark Worth-a-Chat), or reviewed (looked at, keep on
 * record). Once dismissed, the row stops surfacing in the Today tray.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Assignment, AnomalyStatus, api } from "../api";
import { AnomalyStatusChip } from "./StatusChips";

export function GradeAnomalyCard({ a }: { a: Assignment }) {
  const qc = useQueryClient();
  const triedRef = useRef(false);
  const [out, setOut] = useState<{
    anomalous: boolean;
    reason: string;
    explanation: string | null;
  } | null>(
    a.llm_summary
      ? { anomalous: true, reason: "cached", explanation: a.llm_summary }
      : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<AnomalyStatus | null>(
    (a.anomaly_status as AnomalyStatus | null | undefined) ?? null,
  );

  const explain = useMutation({
    mutationFn: (force: boolean) => api.explainGradeAnomaly(a.id, force),
    onSuccess: (r) => {
      setOut({
        anomalous: r.anomalous,
        reason: r.reason,
        explanation: r.explanation,
      });
      if (r.explanation) {
        qc.invalidateQueries({ queryKey: ["grades"] });
      }
    },
    onError: (e) => setError(String(e)),
  });

  const setStatusMut = useMutation({
    mutationFn: (s: AnomalyStatus | null) => api.setAnomalyStatus(a.id, s),
    onSuccess: (r) => {
      setStatus(r.status);
      qc.invalidateQueries({ queryKey: ["grades"] });
      qc.invalidateQueries({ queryKey: ["anomalies"] });
    },
  });

  useEffect(() => {
    if (out) return;
    if (triedRef.current) return;
    if (a.kind !== "grade") return;
    triedRef.current = true;
    explain.mutate(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.id, a.kind]);

  if (a.kind !== "grade") return null;
  if (!out && !explain.isPending && !error) return null;

  // Not anomalous → render nothing (silence is the right answer).
  if (out && !out.anomalous) return null;

  const dismissed = status === "dismissed";

  return (
    <section
      className={
        "mb-4 px-3 py-2 rounded border " +
        (dismissed
          ? "border-gray-200 bg-gray-50/60"
          : "border-red-200 bg-red-50/60")
      }
    >
      <div className="flex items-start gap-2 flex-wrap">
        <span
          className={
            "text-[10px] uppercase tracking-wider font-semibold mt-0.5 " +
            (dismissed ? "text-gray-500" : "text-red-700")
          }
        >
          {dismissed ? "Off-trend (dismissed)" : "Off-trend grade"}
        </span>
        {status && status !== "open" && (
          <AnomalyStatusChip status={status} />
        )}
        <button
          type="button"
          onClick={() => {
            setError(null);
            explain.mutate(true);
          }}
          className="ml-auto text-[10px] text-gray-500 hover:text-gray-800 disabled:opacity-50"
          disabled={explain.isPending}
          title="Regenerate the hypothesis"
        >
          ↻
        </button>
      </div>
      {explain.isPending && !out?.explanation ? (
        <div className="text-sm text-gray-500 italic mt-1">
          Asking Claude for a hypothesis…
        </div>
      ) : out?.explanation ? (
        <>
          <div className="text-sm text-gray-900 mt-1 leading-snug">
            {out.explanation}
          </div>
          <div className="text-[10px] text-gray-500 mt-1">{out.reason}</div>
        </>
      ) : (
        <div className="text-xs text-gray-500 italic mt-1">
          {error || "No hypothesis available."}
        </div>
      )}
      <div className="flex gap-2 mt-2 text-[11px]">
        <ActionBtn
          label="Dismiss"
          title="Clear the flag — no concern"
          active={status === "dismissed"}
          disabled={setStatusMut.isPending}
          onClick={() => setStatusMut.mutate("dismissed")}
        />
        <ActionBtn
          label="Mark reviewed"
          title="Looked at it, no action needed but keep on record"
          active={status === "reviewed"}
          disabled={setStatusMut.isPending}
          onClick={() => setStatusMut.mutate("reviewed")}
        />
        <ActionBtn
          label="Escalate"
          title="Worth a chat at PTM / follow up"
          active={status === "escalated"}
          disabled={setStatusMut.isPending}
          onClick={() => setStatusMut.mutate("escalated")}
        />
        {status && (
          <button
            type="button"
            disabled={setStatusMut.isPending}
            onClick={() => setStatusMut.mutate(null)}
            className="ml-auto text-gray-400 hover:text-gray-700 disabled:opacity-50"
            title="Clear all acknowledgement"
          >
            reset
          </button>
        )}
      </div>
    </section>
  );
}

function ActionBtn({
  label,
  title,
  active,
  disabled,
  onClick,
}: {
  label: string;
  title: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={
        "px-2 py-0.5 rounded border text-[11px] disabled:opacity-50 " +
        (active
          ? "bg-gray-800 text-white border-gray-800"
          : "bg-white text-gray-700 border-gray-300 hover:border-gray-500")
      }
    >
      {label}
    </button>
  );
}

