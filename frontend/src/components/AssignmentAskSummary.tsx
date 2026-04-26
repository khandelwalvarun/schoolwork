/**
 * AssignmentAskSummary — the Claude-extracted "the ask in plain English"
 * line that sits above the raw Description in the AuditDrawer.
 *
 * Auto-fires summarize on first open if the assignment has a body but
 * no cached llm_summary. Subsequent opens read the cached value
 * instantly.
 *
 * Falls back to silence (no card rendered) if Claude is unreachable
 * or the body is too short to be worth compressing — better than a
 * misleading summary.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Assignment, api } from "../api";

export function AssignmentAskSummary({ a }: { a: Assignment }) {
  const qc = useQueryClient();
  const triedRef = useRef(false);
  const [summary, setSummary] = useState<string | null>(a.llm_summary ?? null);
  const [error, setError] = useState<string | null>(null);

  const summarize = useMutation({
    mutationFn: (force: boolean) => api.summarizeAssignment(a.id, force),
    onSuccess: (out) => {
      if (out.summary) {
        setSummary(out.summary);
        // Invalidate any queries that show this assignment so the
        // cached llm_summary lands in the next render.
        qc.invalidateQueries({ queryKey: ["today"] });
        qc.invalidateQueries({ queryKey: ["child-detail"] });
      } else if (!out.cached && !out.llm_used) {
        setError("body too short to compress");
      } else if (out.llm_used && !out.summary) {
        setError("LLM returned an empty summary");
      }
    },
    onError: (e) => setError(String(e)),
  });

  useEffect(() => {
    if (summary) return;
    if (triedRef.current) return;
    if (!a.body || a.body.trim().length < 30) return;
    triedRef.current = true;
    summarize.mutate(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.id]);

  if (!summary && !summarize.isPending && !error) return null;

  return (
    <div className="mb-2 px-3 py-2 rounded border border-purple-200 bg-purple-50/60">
      <div className="flex items-start gap-2">
        <span className="text-[10px] uppercase tracking-wider text-purple-700 font-semibold mt-0.5">
          The ask
        </span>
        <button
          type="button"
          onClick={() => {
            setError(null);
            summarize.mutate(true);
          }}
          className="ml-auto text-[10px] text-gray-500 hover:text-gray-800 disabled:opacity-50"
          disabled={summarize.isPending}
          title="Regenerate via Claude"
        >
          ↻
        </button>
      </div>
      {summarize.isPending && !summary ? (
        <div className="text-sm text-gray-500 italic mt-1">
          Asking Claude for a 1-line distillation…
        </div>
      ) : summary ? (
        <div className="text-sm text-gray-900 mt-1 leading-snug">
          {summary}
        </div>
      ) : (
        <div className="text-xs text-gray-500 italic mt-1">{error}</div>
      )}
    </div>
  );
}
