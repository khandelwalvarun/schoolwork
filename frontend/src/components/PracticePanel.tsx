/**
 * PracticePanel — slide-over workspace for iterative LLM cowork.
 *
 * Two flavours via the `kind` prop:
 *   review_prep      — "📝 prep": practice sheet of questions for an
 *                      upcoming review/test
 *   assignment_help  — "💡 help": outline / hints / worked example for
 *                      an existing assignment the kid has to do
 *
 * Both share the same iteration / classwork-scan / preferred-pointer
 * plumbing — only the rendering of `output_json` and the chrome
 * (title / quick-prompt suggestions) change.
 *
 * The parent can:
 *   - Read the active iteration as STRUCTURED CARDS (questions for
 *     review_prep, sections for assignment_help) — not raw markdown
 *   - Switch between iterations via chips
 *   - Star a different iteration as canonical
 *   - Print a clean printable version (opens in a new window)
 *   - Copy the markdown to clipboard
 *   - Drag-drop classwork scans into the panel — Vision OCR runs inline
 *   - Issue a refinement prompt at the bottom; quick-prompt buttons
 *     let you jump-start common asks ("harder", "in Hindi", etc.)
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  Assignment,
  PracticeHelpSection,
  PracticeKind,
  PracticeSessionOut,
  PracticeQuestion,
} from "../api";

type Mode =
  | { kind: "loading-existing" }
  | { kind: "needs-start" }
  | { kind: "active"; sessionId: number };

const QUICK_PROMPTS_REVIEW = [
  "Harder",
  "Easier",
  "More word problems",
  "Fewer questions (5 max)",
  "In Hindi",
  "Add worked solutions",
  "Mixed difficulty",
];

const QUICK_PROMPTS_HELP = [
  "Give me an outline",
  "Show a worked example",
  "Just hints, don't solve it",
  "Reading guide",
  "Brainstorm starter",
  "Vocab list",
  "In Hindi",
  "Shorter",
  "More structure",
];

export function PracticePanel({
  childId,
  subject,
  linkedAssignment,
  topic,
  initialPrompt,
  existingSessionId,
  kind = "review_prep",
  onClose,
}: {
  childId: number;
  subject: string;
  linkedAssignment?: Assignment | null;
  topic?: string | null;
  initialPrompt?: string | null;
  existingSessionId?: number | null;
  kind?: PracticeKind;
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
  const [dragHover, setDragHover] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dropZoneRef = useRef<HTMLDivElement | null>(null);

  const isHelp = kind === "assignment_help";
  const accentColor = isHelp ? "amber" : "purple";
  const accentLabel = isHelp ? "💡 Assignment help" : "📝 Practice prep";
  const quickPrompts = isHelp ? QUICK_PROMPTS_HELP : QUICK_PROMPTS_REVIEW;

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Look for an existing session for this (child × subject × linked-row × kind).
  useEffect(() => {
    if (mode.kind !== "loading-existing") return;
    let cancelled = false;
    (async () => {
      try {
        const sessions = await api.practiceListSessions(childId, subject);
        if (cancelled) return;
        const matches = sessions.filter((s) => s.kind === kind);
        const match =
          (linkedAssignment &&
            matches.find((s) => s.linked_assignment_id === linkedAssignment.id)) ||
          matches[0];
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
  }, [mode.kind, childId, subject, linkedAssignment, kind]);

  const sessionId = mode.kind === "active" ? mode.sessionId : null;
  const { data: session } = useQuery<PracticeSessionOut>({
    queryKey: ["practice-session", sessionId],
    queryFn: () => api.practiceGetSession(sessionId!),
    enabled: sessionId !== null,
    refetchOnWindowFocus: false,
  });

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
          ? `${subject} ${isHelp ? "help" : "prep"} — ${linkedAssignment.title || "review"}`
          : `${subject} ${isHelp ? "help" : "prep"}`,
        initial_prompt: initialPrompt ?? null,
        kind,
        use_llm: true,
      });
      setMode({ kind: "active", sessionId: newSession.id });
      setActiveIterIdx(null);
      qc.setQueryData(["practice-session", newSession.id], newSession);
    } catch (e) {
      setErrorMsg(`Failed to start session: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  const iterate = async (overridePrompt?: string) => {
    const promptText = (overridePrompt ?? prompt).trim();
    if (!sessionId || !promptText) return;
    setBusy("Refining draft with Claude Opus…");
    setErrorMsg(null);
    try {
      const updated = await api.practiceIterateSession(sessionId, promptText);
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

  const printIteration = () => {
    if (!activeIter || !session) return;
    const w = window.open("", "_blank", "width=900,height=1100");
    if (!w) return;
    const out = activeIter.output_json;
    const safe = (s: string) => s.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]!));
    let body = "";
    if (session.kind === "assignment_help" && out?.sections) {
      body = `
        ${out.summary ? `<p class="lede">${safe(out.summary)}</p>` : ""}
        ${out.sections.map((s) => `
          <section>
            <h2>${safe(s.heading)}${s.kind ? ` <span class="tag">${safe(s.kind)}</span>` : ""}</h2>
            <pre>${safe(s.body_md)}</pre>
          </section>
        `).join("")}
        ${out.next_steps && out.next_steps.length > 0 ? `
          <section>
            <h2>Next steps</h2>
            <ul>${out.next_steps.map((n) => `<li>${safe(n)}</li>`).join("")}</ul>
          </section>` : ""}
      `;
    } else if (out?.questions) {
      body = `
        ${out.instructions ? `<p class="lede"><em>${safe(out.instructions)}</em></p>` : ""}
        <ol class="qs">
          ${out.questions.map((q) => `
            <li>
              <div class="stem">${safe(q.stem)}${q.marks ? ` <span class="marks">(${q.marks} marks)</span>` : ""}</div>
              ${q.topic_ref ? `<div class="topic">${safe(q.topic_ref)}</div>` : ""}
            </li>`).join("")}
        </ol>
        ${out.answer_key ? `<section class="answers"><h2>Answer key</h2><pre>${safe(out.answer_key)}</pre></section>` : ""}
      `;
    }
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${safe(activeIter.output_json?.title || session.title)}</title>
      <style>
        body { font: 14px/1.55 -apple-system, "Segoe UI", system-ui, sans-serif; max-width: 720px; margin: 24px auto; padding: 0 24px; color: #111; }
        h1 { font-size: 22px; margin: 0 0 4px; }
        .meta { color: #666; font-size: 13px; margin-bottom: 16px; border-bottom: 1px solid #ddd; padding-bottom: 12px; }
        h2 { font-size: 15px; margin: 18px 0 6px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 3px; }
        .tag { font-size: 11px; color: #888; font-weight: 400; text-transform: uppercase; letter-spacing: 0.04em; margin-left: 6px; }
        pre { white-space: pre-wrap; font-family: inherit; margin: 0 0 8px; }
        .lede { color: #333; font-size: 14px; }
        ol.qs { list-style: decimal; padding-left: 20px; }
        ol.qs li { margin: 0 0 18px; padding-left: 4px; }
        ol.qs li .stem { font-weight: 500; }
        ol.qs li .topic { font-size: 11px; color: #888; margin-top: 2px; }
        .marks { font-weight: 400; color: #888; }
        .answers { margin-top: 24px; border-top: 2px solid #ccc; padding-top: 12px; }
        .caveat { color: #888; font-size: 11px; font-style: italic; margin-top: 32px; border-top: 1px solid #eee; padding-top: 12px; }
        @media print { body { margin: 8mm 12mm; padding: 0; } button { display: none; } }
      </style></head><body>
      <button onclick="window.print()" style="float: right; padding: 6px 12px; background: #333; color: white; border: 0; border-radius: 4px; cursor: pointer;">Print</button>
      <h1>${safe(out?.title || session.title)}</h1>
      <div class="meta">${safe(session.subject)}${out?.format ? ` · ${safe(out.format)}` : ""} · iteration #${activeIter.iteration_index}</div>
      ${body}
      ${out?.honest_caveat ? `<div class="caveat">${safe(out.honest_caveat)}</div>` : ""}
    </body></html>`);
    w.document.close();
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragHover(true);
  };
  const onDragLeave = () => setDragHover(false);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragHover(false);
    onUpload(e.dataTransfer.files);
  };

  const headerAccentCls =
    accentColor === "amber" ? "text-amber-700" : "text-purple-700";
  const buttonAccentCls =
    accentColor === "amber"
      ? "bg-amber-700 hover:bg-amber-800"
      : "bg-purple-700 hover:bg-purple-800";

  return (
    <div
      className="fixed inset-0 z-50"
      onClick={onClose}
      style={{ background: "oklch(0% 0 0 / 0.18)" }}
    >
      <aside
        className="slide-over flex flex-col"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(720px, 100vw)" }}
        aria-label="Practice prep"
      >
        <header className="px-5 py-4 border-b border-gray-200 sticky top-0 bg-white flex items-start justify-between gap-3 shrink-0">
          <div className="flex-1 min-w-0">
            <div className={"text-xs uppercase tracking-wider " + headerAccentCls}>
              {accentLabel} · iterative cowork
            </div>
            <h3 className="text-lg font-bold leading-tight truncate">
              {session?.title ||
                (linkedAssignment
                  ? `${subject} — ${linkedAssignment.title}`
                  : `${subject} ${isHelp ? "help" : "prep"}`)}
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
              <>
                <button
                  type="button"
                  onClick={printIteration}
                  className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
                  title="Open print-friendly view"
                >
                  print
                </button>
                <button
                  type="button"
                  onClick={copyMarkdown}
                  className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
                  title="Copy this draft's markdown to clipboard"
                >
                  copy md
                </button>
              </>
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

        <div
          ref={dropZoneRef}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={
            "flex-1 overflow-auto px-5 py-4 space-y-4 relative " +
            (dragHover ? "ring-4 ring-violet-400 ring-inset bg-violet-50/50" : "")
          }
        >
          {dragHover && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-violet-700 text-lg font-medium z-10">
              Drop classwork scans here
            </div>
          )}

          {errorMsg && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
              {errorMsg}
            </div>
          )}

          {mode.kind === "loading-existing" && (
            <div className="text-sm text-gray-500 italic">
              Looking for an existing session…
            </div>
          )}

          {mode.kind === "needs-start" && (
            <StartCard
              isHelp={isHelp}
              subject={subject}
              linkedAssignment={linkedAssignment}
              busy={busy}
              onStart={startNew}
              accentBtnCls={buttonAccentCls}
            />
          )}

          {session && (
            <>
              <IterationSwitcher
                session={session}
                activeIterIdx={activeIterIdx}
                onSelect={setActiveIterIdx}
              />

              {activeIter && (
                <IterationCard
                  iteration={activeIter}
                  isPreferred={activeIter.id === session.preferred_iteration_id}
                  onStar={() => setPreferred(activeIter.id)}
                  isHelp={session.kind === "assignment_help"}
                />
              )}

              <ScansSection
                scans={session.scans}
                onUploadClick={() => fileInputRef.current?.click()}
              />
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,application/pdf"
                className="hidden"
                onChange={(e) => onUpload(e.target.files)}
              />
            </>
          )}

          {busy && (
            <div className="text-xs text-purple-800 bg-purple-50 border border-purple-200 rounded p-2 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-purple-700 animate-pulse" />
              {busy}
            </div>
          )}
        </div>

        {session && (
          <footer className="border-t border-gray-200 bg-white p-3 shrink-0">
            <div className="flex flex-wrap gap-1.5 mb-2">
              {quickPrompts.map((qp) => (
                <button
                  key={qp}
                  type="button"
                  onClick={() => iterate(qp)}
                  disabled={busy !== null}
                  className="text-[11px] px-2 py-0.5 rounded-full border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                  title={`Iterate with: "${qp}"`}
                >
                  {qp}
                </button>
              ))}
            </div>
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
                placeholder={
                  isHelp
                    ? 'e.g. "show a worked example" · "shorter outline" · "in Hindi" · "match what scan #1 covered"'
                    : 'e.g. "harder, more word problems" · "in Hindi" · "remove Q3" · "match scan #1"'
                }
                className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm resize-none"
                disabled={busy !== null}
              />
              <button
                type="button"
                onClick={() => iterate()}
                disabled={busy !== null || !prompt.trim()}
                className={
                  "px-3 py-1 rounded text-white disabled:opacity-50 self-stretch " +
                  buttonAccentCls
                }
                title="⌘+Enter to send"
              >
                Refine
              </button>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">
              ⌘+Enter to send · drop files anywhere in the panel to upload classwork scans · iterations cap at 30 per session
            </div>
          </footer>
        )}
      </aside>
    </div>
  );
}


// ───────────────────────── sub-components ─────────────────────────

function StartCard({
  isHelp,
  subject,
  linkedAssignment,
  busy,
  onStart,
  accentBtnCls,
}: {
  isHelp: boolean;
  subject: string;
  linkedAssignment?: Assignment | null;
  busy: string | null;
  onStart: () => void;
  accentBtnCls: string;
}) {
  return (
    <div className="text-sm space-y-3">
      <p>
        No session yet for <strong>{subject}</strong>
        {linkedAssignment && (
          <>
            {" "}— <em>{linkedAssignment.title}</em>
          </>
        )}
        .
      </p>
      <p className="text-gray-500">
        {isHelp ? (
          <>
            Click below to ask Claude Opus for help on this assignment — an
            outline, hints, a worked example, or whatever fits the format. You
            can then iterate with prompts (<em>"give me an outline"</em>,
            <em>"shorter"</em>, <em>"in Hindi"</em>) and upload classwork scans
            so the next round matches what's been covered.
          </>
        ) : (
          <>
            Click below to ask Claude Opus for a first draft. You can then
            iterate with prompts (<em>"harder"</em>, <em>"remove Q3"</em>,{" "}
            <em>"more word problems"</em>) and upload classwork scans to
            ground the next round in what was actually covered.
          </>
        )}
      </p>
      <button
        type="button"
        onClick={onStart}
        disabled={busy !== null}
        className={"px-3 py-1.5 rounded text-white disabled:opacity-60 " + accentBtnCls}
      >
        {busy ?? `Generate first ${isHelp ? "draft" : "draft"}`}
      </button>
    </div>
  );
}

function IterationSwitcher({
  session,
  activeIterIdx,
  onSelect,
}: {
  session: PracticeSessionOut;
  activeIterIdx: number | null;
  onSelect: (idx: number) => void;
}) {
  return (
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
            onClick={() => onSelect(it.iteration_index)}
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
  );
}

function IterationCard({
  iteration,
  isPreferred,
  onStar,
  isHelp,
}: {
  iteration: { id: number; iteration_index: number; parent_prompt: string | null;
               output_json: ReturnType<typeof JSON.parse> | null; output_md: string;
               llm_used: boolean; llm_model: string | null; duration_ms: number | null };
  isPreferred: boolean;
  onStar: () => void;
  isHelp: boolean;
}) {
  const out = iteration.output_json;

  return (
    <article className="border border-gray-200 rounded-lg bg-white shadow-sm">
      {iteration.parent_prompt && (
        <div className="px-3 py-2 border-b border-gray-100 text-xs text-gray-700 bg-amber-50">
          <span className="text-[10px] uppercase tracking-wider text-amber-700 mr-1.5">
            Prompt
          </span>
          {iteration.parent_prompt}
        </div>
      )}

      <div className="px-5 py-4 space-y-3">
        {out?.title && (
          <h4 className="text-base font-semibold leading-tight">{out.title}</h4>
        )}

        {isHelp ? (
          <HelpBody out={out} />
        ) : (
          <ReviewBody out={out} fallback={iteration.output_md} />
        )}

        {out?.honest_caveat && (
          <div className="text-[11px] text-gray-500 italic border-t border-gray-100 pt-2">
            {out.honest_caveat}
          </div>
        )}
      </div>

      <div className="px-4 py-2 border-t border-gray-100 flex items-center gap-2 text-xs text-gray-500">
        <span>
          {iteration.llm_used ? iteration.llm_model : "rule fallback"}
          {iteration.duration_ms != null
            ? ` · ${(iteration.duration_ms / 1000).toFixed(1)}s`
            : ""}
        </span>
        <button
          type="button"
          onClick={onStar}
          disabled={isPreferred}
          className="ml-auto px-2 py-0.5 rounded border border-amber-300 text-amber-800 hover:bg-amber-50 disabled:opacity-50"
          title="Star this draft as the canonical version"
        >
          {isPreferred ? "★ starred" : "☆ star"}
        </button>
      </div>
    </article>
  );
}

function ReviewBody({ out, fallback }: { out: any; fallback: string }) {
  if (!out || !Array.isArray(out.questions)) {
    return <pre className="text-sm leading-relaxed whitespace-pre-wrap font-sans">{fallback}</pre>;
  }
  const totalMarks = out.questions.reduce((s: number, q: PracticeQuestion) => s + (q.marks || 0), 0);
  return (
    <>
      {out.instructions && (
        <p className="text-sm text-gray-700 italic">{out.instructions}</p>
      )}
      <div className="text-xs text-gray-500">
        {out.questions.length} questions{totalMarks ? ` · ${totalMarks} marks total` : ""}
      </div>
      <ol className="space-y-3 list-decimal pl-5">
        {out.questions.map((q: PracticeQuestion) => (
          <li key={q.n} className="text-sm">
            <div className="font-medium leading-snug">
              {q.stem}
              {q.marks ? (
                <span className="ml-2 text-xs text-gray-500 font-normal">
                  ({q.marks} marks)
                </span>
              ) : null}
            </div>
            {q.topic_ref && (
              <div className="text-[11px] text-gray-500 mt-0.5">
                ↳ {q.topic_ref}
              </div>
            )}
            {q.expected_answer && (
              <details className="mt-1 text-xs text-gray-600">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-800">
                  show expected answer
                </summary>
                <div className="mt-1 pl-2 border-l-2 border-gray-200">
                  {q.expected_answer}
                  {q.expected_solution_md && (
                    <pre className="whitespace-pre-wrap font-sans mt-1">
                      {q.expected_solution_md}
                    </pre>
                  )}
                </div>
              </details>
            )}
          </li>
        ))}
      </ol>
      {out.answer_key && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-gray-600 hover:text-gray-800 font-medium">
            Answer key
          </summary>
          <pre className="mt-1 text-xs whitespace-pre-wrap font-sans bg-gray-50 p-3 rounded border border-gray-200">
            {out.answer_key}
          </pre>
        </details>
      )}
    </>
  );
}

function HelpBody({ out }: { out: any }) {
  if (!out || !Array.isArray(out.sections)) {
    return <div className="text-sm text-gray-500 italic">No structured output yet.</div>;
  }
  const sectionToneCls = (k?: string) => {
    switch (k) {
      case "step": return "border-blue-200 bg-blue-50/40";
      case "example": return "border-emerald-200 bg-emerald-50/40";
      case "hint": return "border-amber-200 bg-amber-50/40";
      case "warning": return "border-rose-200 bg-rose-50/40";
      case "reference": return "border-gray-200 bg-gray-50";
      case "optional": return "border-gray-200 bg-white";
      default: return "border-gray-200 bg-white";
    }
  };
  return (
    <>
      {out.summary && (
        <p className="text-sm text-gray-700 italic">{out.summary}</p>
      )}
      {out.format && (
        <div className="text-xs">
          <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
            format · {out.format}
          </span>
        </div>
      )}
      <div className="space-y-3">
        {out.sections.map((s: PracticeHelpSection, i: number) => (
          <section
            key={i}
            className={"border rounded p-3 " + sectionToneCls(s.kind)}
          >
            <h5 className="text-sm font-semibold mb-1 flex items-center gap-2">
              {s.heading}
              {s.kind && (
                <span className="text-[10px] uppercase tracking-wider text-gray-500 font-normal">
                  {s.kind}
                </span>
              )}
            </h5>
            <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed text-gray-800">
              {s.body_md}
            </pre>
          </section>
        ))}
      </div>
      {out.next_steps && out.next_steps.length > 0 && (
        <section className="border border-violet-200 rounded p-3 bg-violet-50/30">
          <h5 className="text-sm font-semibold mb-1 text-violet-900">Next steps</h5>
          <ul className="text-sm space-y-0.5 list-disc pl-5">
            {out.next_steps.map((n: string, i: number) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function ScansSection({
  scans,
  onUploadClick,
}: {
  scans: PracticeSessionOut["scans"];
  onUploadClick: () => void;
}) {
  return (
    <section className="border border-violet-200 rounded-lg bg-violet-50/30 p-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-violet-800">
          📎 Classwork scans · {scans.length}
        </h4>
        <button
          type="button"
          onClick={onUploadClick}
          className="text-xs px-2 py-1 border border-violet-300 rounded hover:bg-violet-100"
        >
          Upload
        </button>
      </div>
      {scans.length === 0 ? (
        <p className="text-xs text-gray-500 italic">
          Drop photos / PDFs anywhere in this panel — notebook pages, blackboard
          photos, worksheets — and the next iteration uses them as grounding for
          what's been covered in class.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {scans.map((s) => (
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
                <div className="text-gray-600">{s.extracted_summary}</div>
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
  );
}
