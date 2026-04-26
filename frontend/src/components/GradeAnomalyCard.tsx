/**
 * GradeAnomalyCard — Claude-generated hypothesis when a grade landed
 * off the kid's subject trend.
 *
 * Detection is deterministic (services/anomaly.py: ≥12pt delta or 1.5σ
 * with min 2 peers). Only renders when the row is a grade AND the
 * detection fires. Auto-fires explain on first open if no cached text.
 *
 * The hypothesis is one of: time pressure, format change, concept gap,
 * outlier-the-trend-absorbs, first-after-topic-shift. Never behavioural
 * attribution.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Assignment, api } from "../api";

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

  return (
    <section className="mb-4 px-3 py-2 rounded border border-red-200 bg-red-50/60">
      <div className="flex items-start gap-2">
        <span className="text-[10px] uppercase tracking-wider text-red-700 font-semibold mt-0.5">
          Off-trend grade
        </span>
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
    </section>
  );
}
