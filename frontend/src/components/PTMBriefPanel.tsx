/**
 * PTMBriefPanel — slide-over showing the per-subject PTM prep brief.
 *
 * Per-subject sections (current state + talking points + teacher
 * questions) followed by general questions and what-to-ignore. A
 * download button copies the rendered markdown to the clipboard.
 *
 * First open triggers the Claude call (~30-60s). Subsequent opens
 * during the same session are fresh (no client-side cache; the brief
 * is short enough that re-fetching is fine).
 *
 * Closes on Esc, backdrop click, or × button. Same slide-over CSS
 * class as TopicDetailPanel.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

type Brief = Awaited<ReturnType<typeof api.ptmBrief>>;

export function PTMBriefPanel({
  childId,
  onClose,
}: {
  childId: number;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { data, isLoading, error } = useQuery<Brief>({
    queryKey: ["ptm-brief", childId],
    queryFn: () => api.ptmBrief(childId),
    staleTime: 30 * 60_000,  // 30 min
    retry: false,
  });

  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      const md = await api.ptmBriefMarkdown(childId);
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50"
      onClick={onClose}
      style={{ background: "oklch(0% 0 0 / 0.18)" }}
    >
      <aside
        className="slide-over"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(560px, 100vw)" }}
        aria-label="PTM brief"
      >
        <header className="px-5 py-4 border-b border-gray-200 sticky top-0 bg-white flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-xs uppercase tracking-wider text-gray-500">
              PTM brief
            </div>
            <h3 className="text-lg font-bold leading-tight">
              {data?.child_name ?? "…"}
              {data?.class_section && (
                <span className="text-gray-500 font-normal"> ({data.class_section})</span>
              )}
            </h3>
            {data && (
              <div className="text-xs text-gray-500 mt-0.5">
                As of {data.as_of}
                {data.llm_used ? " · Claude-driven" : " · rule fallback"}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={handleCopy}
              className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
              title="Copy markdown to clipboard"
              disabled={!data}
            >
              {copied ? "✓ copied" : "copy md"}
            </button>
            <button
              onClick={onClose}
              className="text-2xl text-gray-400 hover:text-gray-700 leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </header>

        <div className="px-5 py-4 space-y-5">
          {isLoading && (
            <div className="space-y-3">
              <div className="text-sm text-gray-500 italic">
                Asking Claude for a one-page meeting brief — this takes ~30 seconds…
              </div>
              <div className="skeleton h-3 w-3/4 rounded" />
              <div className="skeleton h-3 w-2/3 rounded" />
              <div className="skeleton h-3 w-5/6 rounded" />
            </div>
          )}

          {error && (
            <div className="text-sm text-red-700">
              Failed to generate the brief: {String(error)}
            </div>
          )}

          {data && (
            <>
              {data.headline && (
                <p className="text-base font-semibold text-gray-900 leading-snug">
                  {data.headline}
                </p>
              )}

              {data.subjects.map((s) => (
                <section
                  key={s.name}
                  className="border-t border-gray-100 pt-4"
                >
                  <div className="flex items-baseline justify-between gap-2 mb-1">
                    <h4 className="font-semibold text-gray-800">{s.name}</h4>
                    {s.teacher && (
                      <span className="text-xs text-gray-500">{s.teacher}</span>
                    )}
                  </div>
                  {s.current_state && (
                    <p className="text-sm text-gray-800 leading-snug mb-2">
                      {s.current_state}
                    </p>
                  )}
                  {s.talking_points.length > 0 && (
                    <div className="mb-2">
                      <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">
                        Talking points
                      </div>
                      <ul className="space-y-1 text-sm text-gray-800 list-disc pl-5">
                        {s.talking_points.map((tp, i) => (
                          <li key={i}>{tp}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {s.questions_for_teacher.length > 0 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">
                        Questions for the teacher
                      </div>
                      <ul className="space-y-1 text-sm text-gray-800 list-disc pl-5">
                        {s.questions_for_teacher.map((q, i) => (
                          <li key={i}>{q}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </section>
              ))}

              {data.general_questions.length > 0 && (
                <section className="border-t border-gray-100 pt-4">
                  <h4 className="font-semibold text-gray-800 mb-2">
                    General — across subjects
                  </h4>
                  <ul className="space-y-1 text-sm text-gray-800 list-disc pl-5">
                    {data.general_questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </section>
              )}

              {data.things_to_ignore.length > 0 && (
                <section className="border-t border-gray-100 pt-4">
                  <h4 className="font-semibold text-gray-800 mb-2">
                    What to ignore
                  </h4>
                  <ul className="space-y-1 text-sm text-gray-700 list-disc pl-5">
                    {data.things_to_ignore.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </section>
              )}

              <p className="text-[11px] text-gray-500 italic mt-4 leading-snug border-t border-gray-100 pt-3">
                {data.honest_caveat}
              </p>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
