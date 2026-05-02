/**
 * PracticePanel — slide-over workspace for iterative LLM-driven test prep.
 *
 * One panel per (child × subject × linked-review). Inside the panel the
 * parent can:
 *   - Read the most-recent draft (markdown rendered)
 *   - Switch between iterations via small chips along the top
 *   - Star a different iteration as the canonical draft
 *   - Upload classwork scans (drag-drop or click) — each upload triggers
 *     a Vision pass and the result feeds the next iteration
 *   - Issue a refinement prompt at the bottom ("harder", "remove Q3",
 *     "more word problems", "in Hindi"); the panel calls /iterate and
 *     swaps the active iteration to the new one
 *
 * Backed by the /api/practice/* REST endpoints. Claude Opus does the
 * generation; falls through to a rule skeleton when offline.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  Assignment,
  PracticeSessionOut,
} from "../api";

type Mode =
  | { kind: "loading-existing" }
  | { kind: "needs-start" }
  | { kind: "active"; sessionId: number };

export function PracticePanel({
  childId,
  subject,
  linkedAssignment,
  topic,
  initialPrompt,
  existingSessionId,
  onClose,
}: {
  childId: number;
  subject: string;
  linkedAssignment?: Assignment | null;
  topic?: string | null;
  initialPrompt?: string | null;
  existingSessionId?: number | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>(
    existingSessionId
      ? { kind: "active", sessionId: existingSessionId }
      : { kind: "loading-existing" },
  );
  const [activeIterIdx, setActiveIterIdx] = useState<number | null>(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Look for an existing session for this (child × subject × linked-row)
  // before offering to create one fresh.
  useEffect(() => {
    if (mode.kind !== "loading-existing") return;
    let cancelled = false;
    (async () => {
      try {
        const sessions = await api.practiceListSessions(childId, subject);
        if (cancelled) return;
        const match =
          (linkedAssignment &&
            sessions.find(
              (s) => s.linked_assignment_id === linkedAssignment.id,
            )) ||
          sessions[0];  // fallback: most-recent for this subject
        if (match) {
          setMode({ kind: "active", sessionId: match.id });
        } else {
          setMode({ kind: "needs-start" });
        }
      } catch (e) {
        if (!cancelled) {
          setErrorMsg(String(e));
          setMode({ kind: "needs-start" });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode.kind, childId, subject, linkedAssignment]);

  const sessionId = mode.kind === "active" ? mode.sessionId : null;
  const { data: session } = useQuery<PracticeSessionOut>({
    queryKey: ["practice-session", sessionId],
    queryFn: () => api.practiceGetSession(sessionId!),
    enabled: sessionId !== null,
    refetchOnWindowFocus: false,
  });

  // Once a session loads, pick the preferred iteration (or the latest).
  useEffect(() => {
    if (!session || activeIterIdx !== null) return;
    const preferred = session.iterations.find(
      (i) => i.id === session.preferred_iteration_id,
    );
    const target = preferred || session.iterations[session.iterations.length - 1];
    if (target) setActiveIterIdx(target.iteration_index);
  }, [session, activeIterIdx]);

  const activeIter = session?.iterations.find(
    (i) => i.iteration_index === activeIterIdx,
  );

  const startNew = async () => {
    setBusy("Generating first draft (Claude Opus, ~30-60s)…");
    setErrorMsg(null);
    try {
      const newSession = await api.practiceStartSession({
        child_id: childId,
        subject,
        topic: topic ?? null,
        linked_assignment_id: linkedAssignment?.id ?? null,
        title: linkedAssignment
          ? `${subject} prep — ${linkedAssignment.title || "review"}`
          : `${subject} prep`,
        initial_prompt: initialPrompt ?? null,
        use_llm: true,
      });
      setMode({ kind: "active", sessionId: newSession.id });
      setActiveIterIdx(null);
      qc.setQueryData(["practice-session", newSession.id], newSession);
      qc.invalidateQueries({ queryKey: ["practice-sessions-list", childId] });
    } catch (e) {
      setErrorMsg(`Failed to start session: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  const iterate = async () => {
    if (!sessionId || !prompt.trim()) return;
    setBusy(`Refining draft with Claude Opus…`);
    setErrorMsg(null);
    try {
      const updated = await api.practiceIterateSession(sessionId, prompt);
      qc.setQueryData(["practice-session", sessionId], updated);
      const newest = updated.iterations[updated.iterations.length - 1];
      if (newest) setActiveIterIdx(newest.iteration_index);
      setPrompt("");
    } catch (e) {
      setErrorMsg(`Iteration failed: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  const setPreferred = async (iterId: number) => {
    if (!sessionId) return;
    try {
      const updated = await api.practiceSetPreferred(iterId);
      qc.setQueryData(["practice-session", sessionId], updated);
    } catch (e) {
      setErrorMsg(`Failed to star: ${e}`);
    }
  };

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0 || !sessionId) return;
    setBusy(`Uploading ${files.length} scan(s) + extracting…`);
    setErrorMsg(null);
    try {
      await api.practiceUploadScans(
        childId, subject, Array.from(files), sessionId, true,
      );
      qc.invalidateQueries({ queryKey: ["practice-session", sessionId] });
    } catch (e) {
      setErrorMsg(`Upload failed: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  const copyMarkdown = async () => {
    if (!activeIter || !sessionId) return;
    try {
      const md = await api.practiceIterationMarkdown(sessionId, activeIter.id);
      await navigator.clipboard.writeText(md);
      setBusy("✓ copied");
      setTimeout(() => setBusy(null), 1500);
    } catch (e) {
      setErrorMsg(`Copy failed: ${e}`);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50"
      onClick={onClose}
      style={{ background: "oklch(0% 0 0 / 0.18)" }}
    >
      <aside
        className="slide-over flex flex-col"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(640px, 100vw)" }}
        aria-label="Practice prep"
      >
        <header className="px-5 py-4 border-b border-gray-200 sticky top-0 bg-white flex items-start justify-between gap-3 shrink-0">
          <div className="flex-1 min-w-0">
            <div className="text-xs uppercase tracking-wider text-purple-700">
              📝 Practice prep · iterative cowork
            </div>
            <h3 className="text-lg font-bold leading-tight truncate">
              {session?.title ||
                (linkedAssignment
                  ? `${subject} — ${linkedAssignment.title}`
                  : `${subject} prep`)}
            </h3>
            <div className="text-xs text-gray-500 mt-0.5">
              {session
                ? `${session.iterations.length} iteration${session.iterations.length === 1 ? "" : "s"} · ${session.scans.length} classwork scan${session.scans.length === 1 ? "" : "s"}`
                : mode.kind === "loading-existing"
                ? "Looking for existing prep…"
                : "No session yet"}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {session && activeIter && (
              <button
                type="button"
                onClick={copyMarkdown}
                className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
                title="Copy this draft's markdown to clipboard"
              >
                copy md
              </button>
            )}
            <button
              onClick={onClose}
              className="text-2xl text-gray-400 hover:text-gray-700 leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
          {errorMsg && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
              {errorMsg}
            </div>
          )}

          {mode.kind === "loading-existing" && (
            <div className="space-y-3">
              <div className="text-sm text-gray-500 italic">
                Looking for an existing session…
              </div>
            </div>
          )}

          {mode.kind === "needs-start" && (
            <div className="text-sm space-y-3">
              <p>
                No prep session yet for{" "}
                <strong>{subject}</strong>
                {linkedAssignment && (
                  <>
                    {" "}— <em>{linkedAssignment.title}</em>
                  </>
                )}
                .
              </p>
              <p className="text-gray-500">
                Click below to ask Claude Opus for a first draft. You can then
                iterate with prompts ("harder", "remove Q3", "more word
                problems") and upload classwork scans to ground the next
                round in what was actually covered.
              </p>
              <button
                type="button"
                onClick={startNew}
                disabled={busy !== null}
                className="px-3 py-1.5 rounded bg-purple-700 text-white hover:bg-purple-800 disabled:opacity-60"
              >
                {busy ?? "Generate first draft"}
              </button>
            </div>
          )}

          {session && (
            <>
              {/* Iteration switcher */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[10px] uppercase tracking-wider text-gray-500">
                  Drafts:
                </span>
                {session.iterations.map((it) => {
                  const isActive = it.iteration_index === activeIterIdx;
                  const isPreferred = it.id === session.preferred_iteration_id;
                  return (
                    <button
                      key={it.id}
                      onClick={() => setActiveIterIdx(it.iteration_index)}
                      className={
                        "text-xs px-2 py-1 rounded border " +
                        (isActive
                          ? "border-purple-500 bg-purple-50 text-purple-900 font-medium"
                          : "border-gray-300 text-gray-600 hover:bg-gray-50")
                      }
                      title={
                        it.parent_prompt
                          ? `Iteration ${it.iteration_index} — prompt: ${it.parent_prompt}`
                          : `Iteration ${it.iteration_index} — initial draft`
                      }
                    >
                      {isPreferred ? "★ " : ""}#{it.iteration_index}
                      {it.llm_used ? "" : " (rule)"}
                    </button>
                  );
                })}
              </div>

              {activeIter && (
                <article className="border border-gray-200 rounded-lg bg-white">
                  {activeIter.parent_prompt && (
                    <div className="px-3 py-2 border-b border-gray-100 text-xs text-gray-600 bg-gray-50">
                      <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1.5">
                        Prompt
                      </span>
                      {activeIter.parent_prompt}
                    </div>
                  )}
                  <pre className="px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap font-sans">
                    {activeIter.output_md}
                  </pre>
                  <div className="px-4 py-2 border-t border-gray-100 flex items-center gap-2 text-xs text-gray-500">
                    <span>
                      {activeIter.llm_used ? `${activeIter.llm_model}` : "rule fallback"}
                      {activeIter.duration_ms != null
                        ? ` · ${(activeIter.duration_ms / 1000).toFixed(1)}s`
                        : ""}
                    </span>
                    <button
                      type="button"
                      onClick={() => setPreferred(activeIter.id)}
                      disabled={activeIter.id === session.preferred_iteration_id}
                      className="ml-auto px-2 py-0.5 rounded border border-amber-300 text-amber-800 hover:bg-amber-50 disabled:opacity-50"
                      title="Star this draft as the canonical version"
                    >
                      {activeIter.id === session.preferred_iteration_id
                        ? "★ starred"
                        : "☆ star"}
                    </button>
                  </div>
                </article>
              )}

              {/* Classwork scans */}
              <section className="border border-violet-200 rounded-lg bg-violet-50/30 p-3">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-violet-800">
                    📎 Classwork scans · {session.scans.length}
                  </h4>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="text-xs px-2 py-1 border border-violet-300 rounded hover:bg-violet-100"
                  >
                    Upload
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/*,application/pdf"
                    className="hidden"
                    onChange={(e) => onUpload(e.target.files)}
                  />
                </div>
                {session.scans.length === 0 ? (
                  <p className="text-xs text-gray-500 italic">
                    Upload photos of recent classwork — notebook pages, blackboard
                    photos, worksheets — and the next iteration will use them as
                    grounding for what's been covered in class.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {session.scans.map((s) => (
                      <li
                        key={s.id}
                        className="text-xs px-2 py-1 bg-white rounded border border-violet-100"
                      >
                        <div className="font-medium text-gray-700 mb-0.5">
                          Scan #{s.id}{" "}
                          <span className="text-gray-400 font-normal">
                            · {new Date(s.uploaded_at || "").toLocaleString()}
                          </span>
                        </div>
                        {s.extracted_summary ? (
                          <div className="text-gray-600">
                            {s.extracted_summary}
                          </div>
                        ) : (
                          <div className="text-gray-400 italic">
                            {s.extracted_at
                              ? "extraction returned no summary"
                              : "Vision extraction pending…"}
                          </div>
                        )}
                        {s.extracted_topics && s.extracted_topics.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {s.extracted_topics.map((t) => (
                              <span
                                key={t}
                                className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-800"
                              >
                                {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}

          {busy && (
            <div className="text-xs text-purple-800 bg-purple-50 border border-purple-200 rounded p-2 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-purple-700 animate-pulse" />
              {busy}
            </div>
          )}
        </div>

        {/* Iterative prompt at the bottom — always visible when a session
            is active. Disabled when busy. */}
        {session && (
          <footer className="border-t border-gray-200 bg-white p-3 shrink-0">
            <label className="text-[10px] uppercase tracking-wider text-gray-500 block mb-1">
              Refine with a prompt
            </label>
            <div className="flex gap-2">
              <textarea
                rows={2}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    iterate();
                  }
                }}
                placeholder='e.g. "harder, more word problems" · "in Hindi" · "remove Q3" · "match what scan #1 shows"'
                className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm resize-none"
                disabled={busy !== null}
              />
              <button
                type="button"
                onClick={iterate}
                disabled={busy !== null || !prompt.trim()}
                className="px-3 py-1 rounded bg-purple-700 text-white hover:bg-purple-800 disabled:opacity-50 self-stretch"
                title="⌘+Enter to send"
              >
                Refine
              </button>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">
              ⌘+Enter to send · iterations cap at 30 per session · Opus
              processes ~30-60s per round
            </div>
          </footer>
        )}
      </aside>
    </div>
  );
}
