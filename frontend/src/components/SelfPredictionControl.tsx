/**
 * SelfPredictionControl — three-band picker plus an outcome badge.
 *
 * Pre-grade: kid taps high / mid / low. The choice persists to the
 * assignment row (POST /api/assignments/:id/self-prediction).
 *
 * Post-grade: when a grade is linked to the assignment via grade_match,
 * the backend computes outcome ∈ {matched, better, worse}. We show the
 * outcome inline as a small chip — green for matched, blue for better,
 * red for worse — together with the original prediction so the kid can
 * see the calibration loop close.
 *
 * Design choice: tiny, low-stakes, removable. The Zimmerman research is
 * adamant that self-prediction is a *practice*, not a graded
 * performance — making it a heavyweight modal would defeat the loop.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Assignment, SelfPredictionBand, SelfPredictionOutcome, api } from "../api";

type Band = "high" | "mid" | "low";

const BAND_META: Record<Band, { label: string; tone: string; range: string }> = {
  high: {
    label: "High",
    tone: "border-blue-300 text-blue-800 bg-blue-50",
    range: "≥ 85%",
  },
  mid: {
    label: "Mid",
    tone: "border-amber-300 text-amber-800 bg-amber-50",
    range: "70–85%",
  },
  low: {
    label: "Low",
    tone: "border-gray-300 text-gray-800 bg-gray-50",
    range: "< 70%",
  },
};

const OUTCOME_META: Record<SelfPredictionOutcome, { label: string; tone: string }> = {
  matched: { label: "matched", tone: "border-green-300 text-green-800 bg-green-50" },
  better:  { label: "better",  tone: "border-blue-300  text-blue-800  bg-blue-50"  },
  worse:   { label: "worse",   tone: "border-red-300   text-red-800   bg-red-50"   },
};

function isNamedBand(p: SelfPredictionBand | null | undefined): p is Band {
  return p === "high" || p === "mid" || p === "low";
}

export function SelfPredictionControl({ a }: { a: Assignment }) {
  const qc = useQueryClient();
  const setMut = useMutation({
    mutationFn: (band: Band | null) => api.setSelfPrediction(a.id, band),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["assignments"] });
      qc.invalidateQueries({ queryKey: ["self-prediction"] });
    },
  });

  const current = isNamedBand(a.self_prediction) ? a.self_prediction : null;
  const outcome = a.self_prediction_outcome ?? null;

  return (
    <section>
      <div className="text-xs font-semibold text-gray-500 uppercase mb-1">
        Predict (before the grade)
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {(["high", "mid", "low"] as const).map((b) => {
          const meta = BAND_META[b];
          const active = current === b;
          return (
            <button
              key={b}
              type="button"
              disabled={setMut.isPending}
              onClick={() => setMut.mutate(active ? null : b)}
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs border ${
                active ? meta.tone + " ring-2 ring-offset-1 ring-current/40" : "border-gray-200 text-gray-500 hover:bg-gray-50"
              }`}
              title={`${meta.label} band — ${meta.range}`}
            >
              {meta.label} <span className="ml-1 text-[10px] opacity-70">{meta.range}</span>
            </button>
          );
        })}
        {current && outcome && (
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${
              OUTCOME_META[outcome].tone
            }`}
            title="Outcome compared to the prediction"
          >
            outcome · {OUTCOME_META[outcome].label}
          </span>
        )}
        {current && !outcome && (
          <span className="text-[11px] text-gray-400 italic">
            grade not yet linked
          </span>
        )}
      </div>
      {current && (
        <div className="text-[11px] text-gray-400 mt-1">
          Practice loop — your prediction is private to this row.
        </div>
      )}
    </section>
  );
}
