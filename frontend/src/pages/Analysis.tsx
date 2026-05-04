/**
 * /analysis — "Ask Claude" page.
 *
 * Free-form LLM analysis over the parent-cockpit data. The parent
 * types a question; the backend pulls together relevant grades /
 * assignments / comments / messages / patterns / anomalies /
 * mindspark for the chosen scope, sends to Claude Opus, and returns
 * structured findings + suggestions + caveats.
 *
 * Layout:
 *   ┌──────────────────────┬──────────────┐
 *   │  Active analysis     │  History     │
 *   │  + ask box           │  (clickable) │
 *   │                      │              │
 *   └──────────────────────┴──────────────┘
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AnalysisFinding,
  AnalysisOut,
  api,
  Child,
} from "../api";

const SUGGESTED = [
  "What's improving for each kid this month?",
  "Where is each kid struggling most right now?",
  "Anything I should worry about before the next PTM?",
  "Which subjects need more home time this week?",
  "What patterns do you see in the recent grades?",
  "Are there any topics the school covered but didn't test?",
  "How is Tejas's writing trending vs last cycle?",
  "Which assignments needed more parent help than usual?",
];

export default function Analysis() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [childId, setChildId] = useState<number | null>(null);
  const [scopeDays, setScopeDays] = useState(30);
  const [activeId, setActiveId] = useState<number | null>(null);

  const { data: childList } = useQuery({
    queryKey: ["children"],
    queryFn: () => api.children(),
  });
  const { data: history } = useQuery({
    queryKey: ["analysis-history", childId],
    queryFn: () => api.analysisList(childId ?? undefined, 50),
  });
  const { data: active } = useQuery<AnalysisOut>({
    queryKey: ["analysis", activeId],
    queryFn: () => api.analysisGet(activeId!),
    enabled: activeId !== null,
  });

  // When history loads + nothing selected, jump to the latest analysis.
  useEffect(() => {
    if (activeId === null && history && history.length > 0) {
      setActiveId(history[0].id);
    }
  }, [history, activeId]);

  const runMutation = useMutation({
    mutationFn: () =>
      api.analysisRun({
        query: query.trim(),
        child_id: childId,
        scope_days: scopeDays,
        use_llm: true,
      }),
    onSuccess: (created) => {
      qc.setQueryData(["analysis", created.id], created);
      qc.invalidateQueries({ queryKey: ["analysis-history"] });
      setActiveId(created.id);
      setQuery("");
    },
  });

  const submit = () => {
    if (!query.trim() || runMutation.isPending) return;
    runMutation.mutate();
  };

  return (
    <div>
      <header className="mb-4">
        <h2 className="text-2xl font-bold">🔍 Ask Claude</h2>
        <p className="text-sm text-gray-500 mt-1">
          Free-form questions across grades, assignments, comments, messages,
          patterns, and Mindspark — Claude Opus reads what's on file and
          answers with structured findings + caveats. Each analysis is saved
          to the history on the right.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-5">
        {/* Main column — ask + active analysis */}
        <div className="space-y-4 min-w-0">
          <section className="surface p-4 space-y-3">
            <div className="flex flex-wrap gap-2 items-center">
              <ScopeSelect
                childList={childList || []}
                childId={childId}
                onChange={setChildId}
              />
              <DaysSelect days={scopeDays} onChange={setScopeDays} />
              <span className="text-xs text-gray-400 ml-auto">
                Powered by Claude Opus · ~30-60s per question
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setQuery(s)}
                  className="text-[11px] px-2 py-1 rounded-full border border-gray-300 text-gray-700 hover:bg-gray-50"
                >
                  {s}
                </button>
              ))}
            </div>

            <div className="flex gap-2">
              <textarea
                rows={3}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    submit();
                  }
                }}
                placeholder="Ask anything about the kids — grades, patterns, what to focus on, what's improving, what to raise at PTM…"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm resize-none"
              />
              <button
                type="button"
                onClick={submit}
                disabled={!query.trim() || runMutation.isPending}
                className="px-4 py-2 rounded bg-purple-700 hover:bg-purple-800 text-white disabled:opacity-50 self-stretch font-medium"
                title="⌘+Enter to send"
              >
                {runMutation.isPending ? "Asking…" : "Ask"}
              </button>
            </div>
            {runMutation.isError && (
              <div className="text-sm text-red-700">
                Request failed: {String(runMutation.error)}
              </div>
            )}
          </section>

          {runMutation.isPending && (
            <section className="surface p-4">
              <div className="flex items-center gap-2 text-sm text-purple-800">
                <span className="inline-block w-2 h-2 rounded-full bg-purple-700 animate-pulse" />
                Thinking — Claude is reading {scopeDays} days of data…
              </div>
            </section>
          )}

          {active && <ActiveAnalysisCard analysis={active} />}

          {!active && !runMutation.isPending && (
            <section className="surface p-6 text-center text-gray-500 text-sm">
              {history && history.length === 0
                ? "No analyses yet — pick a suggested question above or write your own."
                : "Pick a past analysis from the right, or ask a new question."}
            </section>
          )}
        </div>

        {/* Right rail — history */}
        <aside className="space-y-2 min-w-0">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 px-1">
            History · {history?.length ?? "—"}
          </h3>
          {!history || history.length === 0 ? (
            <p className="text-xs text-gray-400 italic px-1">
              Ask your first question to start a history.
            </p>
          ) : (
            <ul className="space-y-1">
              {history.map((h) => (
                <li key={h.id}>
                  <button
                    type="button"
                    onClick={() => setActiveId(h.id)}
                    className={
                      "w-full text-left px-2.5 py-1.5 rounded text-xs leading-snug border " +
                      (h.id === activeId
                        ? "border-purple-400 bg-purple-50 text-purple-900"
                        : "border-gray-200 hover:bg-gray-50 text-gray-700")
                    }
                  >
                    <div className="font-medium line-clamp-2">{h.query}</div>
                    <div className="text-[10px] text-gray-400 mt-0.5">
                      {h.created_at ? new Date(h.created_at).toLocaleString() : ""}
                      {h.child_id !== null && (
                        <> · scope {scopeChildName(childList, h.child_id)}</>
                      )}
                      {h.scope_days && <> · {h.scope_days}d</>}
                      {!h.llm_used && <> · rule</>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}

function ScopeSelect({
  childList,
  childId,
  onChange,
}: {
  childList: Child[];
  childId: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <select
      value={childId ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      className="text-sm border border-gray-300 rounded px-2 py-1"
      title="Limit the analysis to one kid, or leave 'both' for cross-kid questions"
    >
      <option value="">Both kids</option>
      {childList.map((c) => (
        <option key={c.id} value={c.id}>
          {c.display_name} (Class {c.class_level})
        </option>
      ))}
    </select>
  );
}

function DaysSelect({
  days,
  onChange,
}: {
  days: number;
  onChange: (v: number) => void;
}) {
  return (
    <select
      value={days}
      onChange={(e) => onChange(Number(e.target.value))}
      className="text-sm border border-gray-300 rounded px-2 py-1"
      title="How far back to pull data"
    >
      <option value={7}>Last 7 days</option>
      <option value={14}>Last 14 days</option>
      <option value={30}>Last 30 days</option>
      <option value={60}>Last 60 days</option>
      <option value={90}>Last 90 days</option>
    </select>
  );
}

function scopeChildName(childList: Child[] | undefined, id: number): string {
  return childList?.find((c) => c.id === id)?.display_name || `child ${id}`;
}

function ActiveAnalysisCard({ analysis }: { analysis: AnalysisOut }) {
  const out = analysis.output_json;
  const used = out?.raw_data_used;
  const [copied, setCopied] = useState(false);

  const copyMd = async () => {
    if (!analysis.output_md) return;
    try {
      await navigator.clipboard.writeText(analysis.output_md);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };

  if (!out) {
    return (
      <section className="surface p-4">
        <pre className="text-sm whitespace-pre-wrap font-sans">
          {analysis.output_md || "No output available."}
        </pre>
      </section>
    );
  }

  return (
    <section className="surface overflow-hidden">
      <header className="px-5 py-3 border-b border-gray-100 bg-purple-50/50 flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-purple-700 mb-0.5">
            Q · {analysis.created_at ? new Date(analysis.created_at).toLocaleString() : ""}
          </div>
          <p className="text-sm text-gray-700 italic">"{analysis.query}"</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={copyMd}
            className="text-xs px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50"
            title="Copy markdown to clipboard"
          >
            {copied ? "✓ copied" : "copy md"}
          </button>
        </div>
      </header>

      <div className="px-5 py-4 space-y-4">
        {/* Headline */}
        <p className="text-base font-semibold text-gray-900 leading-snug border-l-4 border-purple-500 pl-3 py-1">
          {out.headline}
        </p>

        {/* Findings */}
        <div className="space-y-2.5">
          {out.findings.map((f: AnalysisFinding, i: number) => (
            <FindingRow key={i} f={f} />
          ))}
        </div>

        {/* Pointers */}
        {out.pointers && out.pointers.length > 0 && (
          <section className="border border-blue-200 rounded p-3 bg-blue-50/40">
            <h5 className="text-sm font-semibold mb-1 text-blue-900">
              💡 Suggested next steps
            </h5>
            <ul className="text-sm space-y-0.5 list-disc pl-5 text-gray-800">
              {out.pointers.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </section>
        )}

        {/* Caveats */}
        {out.caveats && out.caveats.length > 0 && (
          <section className="border border-amber-200 rounded p-3 bg-amber-50/40">
            <h5 className="text-sm font-semibold mb-1 text-amber-900">
              ⚠ Caveats
            </h5>
            <ul className="text-sm space-y-0.5 list-disc pl-5 text-gray-800">
              {out.caveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </section>
        )}

        {/* Footer meta */}
        {used && (
          <div className="text-[11px] text-gray-500 border-t border-gray-100 pt-2 flex flex-wrap gap-x-3 gap-y-0.5">
            <span>{used.children.join(" · ")}</span>
            <span>{used.scope_days}d window</span>
            <span>{used.grades_count} grades</span>
            <span>{used.assignments_count} assignments</span>
            <span>{used.comments_count} comments</span>
            <span>{used.messages_count} messages</span>
            <span className="ml-auto">
              {analysis.llm_used
                ? `${analysis.llm_model} · ${(analysis.duration_ms || 0) / 1000}s`
                : "rule fallback"}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

function FindingRow({ f }: { f: AnalysisFinding }) {
  const tone =
    f.confidence === "high" ? "border-emerald-200 bg-emerald-50/40" :
    f.confidence === "medium" ? "border-gray-200 bg-white" :
    f.confidence === "low" ? "border-amber-200 bg-amber-50/40" :
    "border-gray-200 bg-white";
  return (
    <div className={"border rounded p-3 " + tone}>
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <h5 className="text-sm font-semibold">{f.title}</h5>
        {f.scope && (
          <span className="text-[10px] uppercase tracking-wider text-gray-500">
            {f.scope}
          </span>
        )}
        {f.confidence && (
          <span
            className={
              "text-[10px] px-1.5 py-0.5 rounded " +
              (f.confidence === "high"
                ? "bg-emerald-100 text-emerald-800"
                : f.confidence === "medium"
                ? "bg-gray-100 text-gray-700"
                : "bg-amber-100 text-amber-800")
            }
          >
            {f.confidence}
          </span>
        )}
      </div>
      <p className="text-sm text-gray-800 leading-relaxed">{f.evidence}</p>
    </div>
  );
}
