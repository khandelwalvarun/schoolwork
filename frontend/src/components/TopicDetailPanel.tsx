/**
 * TopicDetailPanel — slide-over showing everything we know about a
 * single (subject, topic) for one kid. Sources joined server-side via
 * /api/topic-detail; this component is purely presentation.
 *
 * Sections (all collapsible/expanded by content presence):
 *   - Header: subject · topic · MasteryPellet · language chip
 *   - Mastery summary line (state, last score, last assessed, attempts)
 *   - Linked grades (most recent first)
 *   - Linked assignments (current + past)
 *   - Portfolio gallery (thumbnails for images, name list for PDFs)
 *
 * Closes on backdrop click, Esc key, or × button.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, Assignment, PortfolioItem, TopicDetail } from "../api";
import { MasteryPellet } from "./MasteryPellet";
import { formatDate } from "../util/dates";

const LANG_PILL: Record<"en" | "hi" | "sa", { label: string; tone: string }> = {
  en: { label: "EN",      tone: "border-blue-300 text-blue-800 bg-blue-50" },
  hi: { label: "हिन्दी", tone: "border-amber-300 text-amber-800 bg-amber-50" },
  sa: { label: "संस्कृत", tone: "border-purple-300 text-purple-800 bg-purple-50" },
};

function MiniGradeRow({ g }: { g: Assignment }) {
  const pct = (g as unknown as { normalized?: { grade_pct?: number } }).normalized?.grade_pct;
  return (
    <li className="flex items-center justify-between text-sm py-1">
      <span className="truncate flex-1 mr-2 text-gray-800">
        {g.title || g.title_en || "(untitled)"}
      </span>
      <span className="text-xs text-gray-500 whitespace-nowrap">
        {pct != null && (
          <span className="font-mono mr-2">{pct.toFixed(0)}%</span>
        )}
        {formatDate(g.due_or_date)}
      </span>
    </li>
  );
}

function MiniAssignmentRow({ a }: { a: Assignment }) {
  return (
    <li className="flex items-center justify-between text-sm py-1">
      <span className="truncate flex-1 mr-2 text-gray-800">
        {a.title || a.title_en || "(untitled)"}
      </span>
      <span className="text-xs text-gray-500 whitespace-nowrap">
        {a.effective_status && (
          <span className="mr-2 italic">{a.effective_status}</span>
        )}
        {formatDate(a.due_or_date)}
      </span>
    </li>
  );
}

function PortfolioThumb({ item }: { item: PortfolioItem }) {
  const isImage = (item.mime_type || "").startsWith("image/");
  const href = `/api/attachments/${item.id}`;
  if (isImage) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="block w-20 h-20 rounded border border-gray-200 overflow-hidden hover:opacity-80"
        title={item.filename}
      >
        <img
          src={href}
          alt={item.filename}
          className="w-full h-full object-cover"
        />
      </a>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="flex flex-col items-center justify-center w-20 h-20 rounded border border-gray-200 text-xs text-gray-700 hover:bg-gray-50"
      title={item.filename}
    >
      <span className="text-2xl" aria-hidden>📄</span>
      <span className="truncate w-full text-center">{item.filename}</span>
    </a>
  );
}

export function TopicDetailPanel({
  childId,
  subject,
  topic,
  onClose,
}: {
  childId: number;
  subject: string;
  topic: string;
  onClose: () => void;
}) {
  // Esc closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { data, isLoading, error } = useQuery<TopicDetail>({
    queryKey: ["topic-detail", childId, subject, topic],
    queryFn: () => api.topicDetail(childId, subject, topic),
    staleTime: 30_000,
  });

  return (
    <div
      className="fixed inset-0 z-50"
      onClick={onClose}
      style={{ background: "oklch(0% 0 0 / 0.18)" }}
    >
      <aside
        className="slide-over"
        onClick={(e) => e.stopPropagation()}
        aria-label={`${topic} — detail`}
      >
        <header className="px-5 py-4 border-b border-gray-200 sticky top-0 bg-white flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-xs uppercase tracking-wider text-gray-500 mb-1">
              {subject}
              {data?.language_code && (
                <span
                  className={`ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${
                    LANG_PILL[data.language_code as "en" | "hi" | "sa"].tone
                  }`}
                >
                  {LANG_PILL[data.language_code as "en" | "hi" | "sa"].label}
                </span>
              )}
            </div>
            <h3 className="text-lg font-bold leading-tight">{topic}</h3>
            {data && (
              <div className="mt-2 flex items-center gap-2 text-sm">
                <MasteryPellet state={data.state} />
                <span className="text-gray-700">
                  {data.state ?? "not yet attempted"}
                  {data.last_score != null && (
                    <> · last <b>{data.last_score.toFixed(0)}%</b></>
                  )}
                  {data.last_assessed_at && (
                    <> · {formatDate(data.last_assessed_at)}</>
                  )}
                  {data.attempt_count > 0 && (
                    <> · {data.attempt_count} item
                      {data.attempt_count === 1 ? "" : "s"}
                    </>
                  )}
                </span>
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-2xl text-gray-400 hover:text-gray-700 leading-none flex-shrink-0"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="px-5 py-4 space-y-5">
          {isLoading && (
            <div className="space-y-2">
              <div className="skeleton h-3 w-1/2 rounded" />
              <div className="skeleton h-3 w-3/4 rounded" />
              <div className="skeleton h-3 w-2/3 rounded" />
            </div>
          )}

          {error && (
            <div className="text-sm text-red-700">
              Failed to load topic detail.
            </div>
          )}

          {data && (
            <>
              {data.linked_grades.length > 0 && (
                <section>
                  <div className="h-section text-gray-700 mb-1">
                    Grades ({data.linked_grades.length})
                  </div>
                  <ul className="divide-y divide-gray-100">
                    {data.linked_grades.map((g) => (
                      <MiniGradeRow key={g.id} g={g} />
                    ))}
                  </ul>
                </section>
              )}

              {data.linked_assignments.length > 0 && (
                <section>
                  <div className="h-section text-gray-700 mb-1">
                    Assignments ({data.linked_assignments.length})
                  </div>
                  <ul className="divide-y divide-gray-100">
                    {data.linked_assignments.map((a) => (
                      <MiniAssignmentRow key={a.id} a={a} />
                    ))}
                  </ul>
                </section>
              )}

              <section>
                <div className="h-section text-gray-700 mb-1">
                  Portfolio ({data.portfolio_items.length})
                </div>
                {data.portfolio_items.length === 0 ? (
                  <div className="text-sm text-gray-500 italic">
                    No items yet. Add photos or scans from the topic row's
                    📎 button.
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {data.portfolio_items.map((it) => (
                      <PortfolioThumb key={it.id} item={it} />
                    ))}
                  </div>
                )}
              </section>

              {data.linked_grades.length === 0 &&
                data.linked_assignments.length === 0 && (
                  <p className="text-sm text-gray-500 italic">
                    No grades or assignments tagged to this topic yet. Items
                    are matched via subject + title-token similarity, so very
                    short or generic titles may not link automatically.
                  </p>
                )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
