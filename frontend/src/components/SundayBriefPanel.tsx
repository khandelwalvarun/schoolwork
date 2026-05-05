/**
 * SundayBriefPanel — slide-over showing the rendered Sunday brief for
 * both kids (or a single kid if childId is given). Markdown rendered
 * as rich text (basic — headings, lists, paragraphs, details).
 *
 * Backed by /api/sunday-brief?format=md which calls services/sunday_brief.py
 * and renders the existing markdown. Same panel pattern as PTMBriefPanel.
 *
 * First open per session triggers the Claude synthesis for both kids
 * (~30-60s). Re-opens within the session use the react-query cache.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export function SundayBriefPanel({
  childId,
  childName,
  onClose,
}: {
  childId?: number;
  childName?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { data, isLoading, error } = useQuery<string>({
    queryKey: ["sunday-brief-md", childId ?? "all"],
    queryFn: () => api.sundayBriefMarkdown(childId),
    staleTime: 30 * 60_000,
    retry: false,
  });

  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-drawer"
      onClick={onClose}
      style={{ background: "oklch(0% 0 0 / 0.18)" }}
    >
      <aside
        className="slide-over"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(620px, 100vw)" }}
        aria-label="Sunday brief"
      >
        <header className="px-5 py-4 border-b border-gray-200 sticky top-0 bg-white flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-xs uppercase tracking-wider text-gray-500">
              Sunday brief
            </div>
            <h3 className="text-lg font-bold leading-tight">
              {childId ? (childName || "This kid") : "Both kids"}
            </h3>
            <div className="text-xs text-gray-500 mt-0.5">
              4 sections: cycle shape · one ask · teacher questions · what to ignore
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={handleCopy}
              className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
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

        <div className="px-5 py-4">
          {isLoading && (
            <div className="space-y-3">
              <div className="text-sm text-gray-500 italic">
                Asking Claude for the weekly synthesis (~30s per kid)…
              </div>
              <div className="skeleton h-3 w-3/4 rounded" />
              <div className="skeleton h-3 w-2/3 rounded" />
              <div className="skeleton h-3 w-5/6 rounded" />
            </div>
          )}
          {error && (
            <div className="text-sm text-red-700">
              Failed: {String(error)}
            </div>
          )}
          {data && (
            <pre className="text-sm text-gray-900 whitespace-pre-wrap leading-relaxed font-sans">
              {data}
            </pre>
          )}
        </div>
      </aside>
    </div>
  );
}
