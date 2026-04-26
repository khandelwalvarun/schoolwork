/**
 * Messages page — Phase 22 dedup view.
 *
 * The school often sends the same announcement once per kid. We collapse
 * those into a single row, tagged with both kids' names, and store the
 * 1-sentence LLM-generated summary on the group (cached on every member
 * row) so a click only invokes Ollama the first time.
 *
 * Click a row → expands a dropdown showing the summary + any link found
 * in the body. If no summary cached yet, the dropdown auto-fires
 * /summarize and shows a spinner. The full title remains visible at the
 * top of the row regardless.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, SchoolMessageGroup } from "../api";
import { formatDate } from "../util/dates";

function KidChip({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border border-purple-300 text-purple-800 bg-purple-50">
      {name}
    </span>
  );
}

export default function Messages() {
  const [openId, setOpenId] = useState<string | null>(null);
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<SchoolMessageGroup[]>({
    queryKey: ["school-messages", "grouped"],
    queryFn: () => api.schoolMessagesGrouped(),
    staleTime: 60_000,
  });

  const summarize = useMutation({
    mutationFn: (groupId: string) => api.schoolMessageSummarize(groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["school-messages", "grouped"] });
    },
  });

  const rows = data ?? [];

  return (
    <div>
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-2xl font-bold">School messages</h2>
        <span className="text-xs text-gray-400">
          {rows.length} group{rows.length === 1 ? "" : "s"} · deduped across kids
        </span>
      </div>

      {isLoading && <div className="text-gray-400">Loading…</div>}
      {!isLoading && rows.length === 0 && (
        <div className="text-gray-500">No messages.</div>
      )}

      <div className="space-y-2">
        {rows.map((g) => {
          const isOpen = openId === g.group_id;
          const hasSummary = !!g.llm_summary;
          const kidNames = g.kids
            .map((k) => k.display_name)
            .filter((n): n is string => !!n);
          return (
            <article
              key={g.group_id}
              className="surface overflow-hidden"
            >
              <button
                type="button"
                className="w-full text-left p-3 hover:bg-gray-50 focus:outline-none focus:ring-1 focus:ring-blue-500"
                onClick={() => {
                  const next = isOpen ? null : g.group_id;
                  setOpenId(next);
                  if (!isOpen && !hasSummary && !summarize.isPending) {
                    summarize.mutate(g.group_id);
                  }
                }}
                aria-expanded={isOpen}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-gray-900 line-clamp-1">
                      {g.title || "(untitled)"}
                    </div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {kidNames.length > 0 && (
                        <span className="flex items-center gap-1">
                          {kidNames.map((n) => <KidChip key={n} name={n} />)}
                        </span>
                      )}
                      {g.member_count > 1 && (
                        <span className="text-[10px] text-gray-400">
                          {g.member_count}× duplicates
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 whitespace-nowrap flex-shrink-0">
                    {formatDate(g.latest_date || g.latest_seen)}
                  </div>
                </div>
              </button>

              {isOpen && (
                <div className="border-t border-gray-200 p-3 bg-gray-50/50 text-sm space-y-2">
                  {hasSummary ? (
                    <>
                      <p className="text-gray-800 leading-relaxed">
                        {g.llm_summary}
                      </p>
                      {g.llm_summary_url && (
                        <a
                          href={g.llm_summary_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-blue-700 hover:underline text-xs break-all"
                        >
                          {g.llm_summary_url}
                        </a>
                      )}
                      <button
                        type="button"
                        className="text-xs text-gray-500 hover:underline"
                        disabled={summarize.isPending}
                        onClick={() => summarize.mutate(g.group_id)}
                      >
                        {summarize.isPending ? "regenerating…" : "regenerate"}
                      </button>
                    </>
                  ) : summarize.isPending ? (
                    <div className="text-gray-500 italic">
                      Asking the local LLM for a 1-sentence summary…
                    </div>
                  ) : (
                    <div className="text-gray-500 italic">
                      No summary yet — click again to generate.
                    </div>
                  )}
                  {g.member_count > 1 && (
                    <details className="text-xs text-gray-500">
                      <summary className="cursor-pointer">
                        Show {g.member_count} member rows
                      </summary>
                      <ul className="mt-1 space-y-0.5 pl-4">
                        {g.members.map((m) => (
                          <li key={m.id}>
                            <span className="text-gray-600">
                              {m.child_name || `child ${m.child_id}`}
                            </span>
                            {" · "}
                            <span className="text-gray-400">
                              first seen {formatDate(m.first_seen_at)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
