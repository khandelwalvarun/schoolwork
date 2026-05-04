/**
 * PracticePanel — slide-over workspace for iterative LLM cowork.
 *
 * Three modes (tabs at the top):
 *   📝 Prep    — practice sheet of questions for an upcoming review
 *   💡 Help    — outline / hints / worked example for an assignment
 *   ✓ Check   — review the kid's COMPLETED work for correctness
 *
 * Each mode is its own session backed by /api/practice/sessions with a
 * different `kind`. Switching tabs swaps to that mode's session for the
 * same (child × subject × linked-assignment) tuple, or offers to start
 * a fresh one. Iterations live inside their own mode and don't bleed
 * across.
 *
 * Polish notes:
 *   - Mode tabs at the top with mode-coloured accents
 *   - Iteration switcher chips with prompt preview tooltips
 *   - Pretty-rendered iteration body per mode (questions / sections /
 *     verdicts), not raw markdown
 *   - Scan tiles with image thumbnails, purpose toggle, drag-drop +
 *     mobile camera capture queue
 *   - Quick-prompt chips per mode + iterative refinement input
 *   - Print + copy + star-iteration affordances in the header
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  Assignment,
  PinnedSource,
  PracticeClassworkScanOut,
  PracticeHelpSection,
  PracticeIterationOut,
  PracticeKind,
  PracticeOutputJson,
  PracticeQuestion,
  PracticeSessionOut,
  ReviewWorkItem,
  ReviewWorkVerdict,
  ScanPurpose,
} from "../api";
import { SourcesPicker } from "./SourcesPicker";

const QUICK_PROMPTS_REVIEW = [
  "Harder", "Easier", "More word problems", "Fewer questions (5 max)",
  "In Hindi", "Add worked solutions", "Mixed difficulty",
];
const QUICK_PROMPTS_HELP = [
  "Give me an outline", "Show a worked example", "Just hints",
  "Reading guide", "Brainstorm starter", "Vocab list",
  "In Hindi", "Shorter", "More structure",
];
const QUICK_PROMPTS_CHECK = [
  "Be gentler", "More specific feedback", "Estimate the score",
  "What should they practice next?", "Focus on Q1-Q3",
  "In Hindi", "Look for handwriting issues",
];

type ModeMeta = {
  kind: PracticeKind;
  label: string;
  emoji: string;
  shortLabel: string;
  ctaCopy: string;
  introHelp: React.ReactNode;
  // Tailwind tone bundle for headers, buttons, accents
  ringCls: string;     // ring colour for active tab
  textCls: string;     // foreground accent
  bgSoft: string;      // soft background for active tab
  buttonCls: string;   // primary CTA button
  pillCls: string;     // chip background for the entry-point button
};

const MODE_DEFS: Record<PracticeKind, ModeMeta> = {
  review_prep: {
    kind: "review_prep",
    label: "Practice prep",
    emoji: "📝",
    shortLabel: "Prep",
    ctaCopy: "Generate practice paper",
    introHelp: (
      <>Generate a practice paper for an upcoming review/test. Iterate with prompts (<em>"harder"</em>, <em>"in Hindi"</em>) and upload classwork scans to ground the next round in what's been covered.</>
    ),
    ringCls: "ring-purple-500",
    textCls: "text-purple-700",
    bgSoft: "bg-purple-50",
    buttonCls: "bg-purple-700 hover:bg-purple-800 text-white",
    pillCls: "bg-purple-100 text-purple-800 border-purple-200 hover:bg-purple-200",
  },
  assignment_help: {
    kind: "assignment_help",
    label: "Assignment help",
    emoji: "💡",
    shortLabel: "Help",
    ctaCopy: "Generate help",
    introHelp: (
      <>Get an outline / worked example / hints / reading guide for this assignment. The LLM picks the format from your prompt — try <em>"give me an outline"</em> or <em>"just hints, don't solve it"</em>.</>
    ),
    ringCls: "ring-amber-500",
    textCls: "text-amber-700",
    bgSoft: "bg-amber-50",
    buttonCls: "bg-amber-600 hover:bg-amber-700 text-white",
    pillCls: "bg-amber-100 text-amber-800 border-amber-200 hover:bg-amber-200",
  },
  review_work: {
    kind: "review_work",
    label: "Check work",
    emoji: "✓",
    shortLabel: "Check",
    ctaCopy: "Review uploaded work",
    introHelp: (
      <>Upload photos of the kid's COMPLETED assignment and Claude reviews it: per-question correctness, feedback, suggestions, and a score estimate. Use the 📷 button below for mobile camera capture, or drag-drop multiple files at once.</>
    ),
    ringCls: "ring-emerald-500",
    textCls: "text-emerald-700",
    bgSoft: "bg-emerald-50",
    buttonCls: "bg-emerald-700 hover:bg-emerald-800 text-white",
    pillCls: "bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-200",
  },
};

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
  kind: initialKind = "review_prep",
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
  const [activeKind, setActiveKind] = useState<PracticeKind>(initialKind);
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
  const [pendingShots, setPendingShots] = useState<File[]>([]);
  // Pinned sources are buffered locally too while the session doesn't
  // exist yet — they get applied immediately after start_session in
  // startNew(). Once a session exists, the canonical source-of-truth
  // is session.pinned_sources from the API.
  const [pendingPinnedSources, setPendingPinnedSources] = useState<PinnedSource[]>([]);
  // Parent's custom instructions for the FIRST iteration. Combined
  // with the mode-specific auto-prompt so the user gets to steer
  // round 1 without losing the grounding hints we already inject.
  const [startPrompt, setStartPrompt] = useState("");
  const [sourcesPickerOpen, setSourcesPickerOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);

  const modeMeta = MODE_DEFS[activeKind];
  const isCheck = activeKind === "review_work";
  // For check mode, scan uploads default to student_work; otherwise classwork_reference.
  const uploadPurpose: ScanPurpose = isCheck ? "student_work" : "classwork_reference";
  const quickPrompts =
    activeKind === "review_prep" ? QUICK_PROMPTS_REVIEW :
    activeKind === "assignment_help" ? QUICK_PROMPTS_HELP :
    QUICK_PROMPTS_CHECK;

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // When the active kind changes, look for an existing session of that kind
  // for this (child × subject × linked_assignment).
  useEffect(() => {
    let cancelled = false;
    setMode({ kind: "loading-existing" });
    setActiveIterIdx(null);
    setPrompt("");
    setPendingShots([]);
    setPendingPinnedSources([]);
    setStartPrompt("");
    (async () => {
      try {
        const sessions = await api.practiceListSessions(childId, subject);
        if (cancelled) return;
        const matches = sessions.filter((s) => s.kind === activeKind);
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
    return () => { cancelled = true; };
  }, [activeKind, childId, subject, linkedAssignment]);

  const sessionId = mode.kind === "active" ? mode.sessionId : null;
  const { data: session } = useQuery<PracticeSessionOut>({
    queryKey: ["practice-session", sessionId],
    queryFn: () => api.practiceGetSession(sessionId!),
    enabled: sessionId !== null,
    refetchOnWindowFocus: false,
  });

  // Fetch the kid row so the SourcesPicker's syllabus tab knows which
  // class_level to fetch the syllabus for. Cheap — children() is a
  // small list and gets cached by react-query.
  const { data: childList } = useQuery({
    queryKey: ["children-for-picker"],
    queryFn: () => api.children(),
    staleTime: 5 * 60_000,
  });
  const childClassLevel =
    childList?.find((c) => c.id === childId)?.class_level ?? null;

  useEffect(() => {
    if (!session) return;
    if (activeIterIdx !== null) return;
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
    setErrorMsg(null);
    const hasShots = pendingShots.length > 0;
    const hasPendingSources = pendingPinnedSources.length > 0;
    const userPrompt = startPrompt.trim();
    // Defer the LLM call when ANYTHING is queued — uploads, source
    // pins, OR a user prompt. Otherwise the start_session call would
    // run round 1 against an empty pack and miss the queued context.
    const deferLlm = hasShots || hasPendingSources || !!userPrompt;
    try {
      setBusy(
        deferLlm
          ? "Creating session…"
          : `Generating first draft (Claude Opus, ~30-60s)…`,
      );
      const newSession = await api.practiceStartSession({
        child_id: childId,
        subject,
        topic: topic ?? null,
        linked_assignment_id: linkedAssignment?.id ?? null,
        title: linkedAssignment
          ? `${subject} ${activeKind === "review_prep" ? "prep" : activeKind === "assignment_help" ? "help" : "check"} — ${linkedAssignment.title || "review"}`
          : `${subject} ${activeKind === "review_prep" ? "prep" : activeKind === "assignment_help" ? "help" : "check"}`,
        initial_prompt: initialPrompt ?? null,
        kind: activeKind,
        use_llm: !deferLlm,
      });
      const newSessionId = newSession.id;
      setMode({ kind: "active", sessionId: newSessionId });
      setActiveIterIdx(null);
      qc.setQueryData(["practice-session", newSessionId], newSession);

      let sessionAfter = newSession;

      // 1. Apply queued source pins (cheap — single API call).
      if (hasPendingSources) {
        setBusy(`Pinning ${pendingPinnedSources.length} source(s)…`);
        sessionAfter = await api.practiceSetSources(
          newSessionId, pendingPinnedSources,
        );
        qc.setQueryData(["practice-session", newSessionId], sessionAfter);
        setPendingPinnedSources([]);
      }

      // 2. Upload queued scans (slower — Vision OCR per file).
      if (hasShots) {
        setBusy(`Uploading ${pendingShots.length} file(s) + extracting…`);
        await api.practiceUploadScans(
          childId, subject, pendingShots, newSessionId, true, uploadPurpose,
        );
        setPendingShots([]);
      }

      // 3. Trigger the first real LLM iteration. The first prompt
      //    combines:
      //      - mode-specific auto-scaffolding (the default we'd send
      //        without any user input)
      //      - grounding clause naming what's queued so Opus knows
      //        to look at scans / pins
      //      - the parent's own instructions, marked clearly so the
      //        LLM treats them as the LEAD steering for round one
      if (deferLlm) {
        setBusy(`Generating first draft with Claude Opus (~30-60s)…`);
        const groundingMentions: string[] = [];
        if (hasShots) groundingMentions.push("uploaded scans");
        if (hasPendingSources) groundingMentions.push("pinned sources");
        const groundingClause = groundingMentions.length > 0
          ? `Use the ${groundingMentions.join(" and ")} as grounding context.`
          : "";
        const baseAuto =
          activeKind === "review_work"
            ? "Review the uploaded student work — give per-question verdicts, feedback, and a score estimate."
            : initialPrompt || groundingClause || "Generate the first draft.";
        const firstPrompt = userPrompt
          ? `${baseAuto}\n\nParent's specific guidance for this round: ${userPrompt}`
          : baseAuto;
        const updated = await api.practiceIterateSession(newSessionId, firstPrompt);
        qc.setQueryData(["practice-session", newSessionId], updated);
        const newest = updated.iterations[updated.iterations.length - 1];
        if (newest) setActiveIterIdx(newest.iteration_index);
        setStartPrompt("");
      }
    } catch (e) {
      setErrorMsg(`Failed to start session: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  const iterate = async (overridePrompt?: string) => {
    const promptText = (overridePrompt ?? prompt).trim();
    if (!sessionId || !promptText) return;
    setBusy(`Refining draft with Claude Opus…`);
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

  const saveSources = async (pinned: PinnedSource[]) => {
    setSourcesPickerOpen(false);
    if (!sessionId) {
      // Pre-session — buffer locally, applied after start_session.
      setPendingPinnedSources(pinned);
      return;
    }
    try {
      const updated = await api.practiceSetSources(sessionId, pinned);
      qc.setQueryData(["practice-session", sessionId], updated);
    } catch (e) {
      setErrorMsg(`Failed to save sources: ${e}`);
    }
  };

  const removePinnedSource = async (idx: number) => {
    if (!sessionId) {
      setPendingPinnedSources((prev) => prev.filter((_, i) => i !== idx));
      return;
    }
    if (!session?.pinned_sources) return;
    const next = session.pinned_sources.filter((_, i) => i !== idx);
    try {
      const updated = await api.practiceSetSources(sessionId, next);
      qc.setQueryData(["practice-session", sessionId], updated);
    } catch (e) {
      setErrorMsg(`Failed to unpin: ${e}`);
    }
  };

  // Upload helpers — take an array of File and either queue them as
  // pending shots (so the user can preview) or upload directly.
  const queueFiles = (files: FileList | File[] | null) => {
    if (!files) return;
    const arr = Array.from(files);
    if (arr.length === 0) return;
    setPendingShots((prev) => [...prev, ...arr]);
  };

  const uploadPending = async () => {
    if (!sessionId || pendingShots.length === 0) return;
    setBusy(`Uploading ${pendingShots.length} file(s) + extracting…`);
    setErrorMsg(null);
    try {
      await api.practiceUploadScans(
        childId, subject, pendingShots, sessionId, true, uploadPurpose,
      );
      setPendingShots([]);
      qc.invalidateQueries({ queryKey: ["practice-session", sessionId] });
    } catch (e) {
      setErrorMsg(`Upload failed: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  const removeFromQueue = (idx: number) => {
    setPendingShots((prev) => prev.filter((_, i) => i !== idx));
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
    openPrintWindow(session, activeIter);
  };

  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragHover(true); };
  const onDragLeave = () => setDragHover(false);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragHover(false);
    queueFiles(e.dataTransfer.files);
  };

  const headerSubtitleParts: string[] = [];
  if (session) {
    headerSubtitleParts.push(
      `${session.iterations.length} iteration${session.iterations.length === 1 ? "" : "s"}`,
    );
    headerSubtitleParts.push(
      `${session.scans.length} scan${session.scans.length === 1 ? "" : "s"}`,
    );
  } else if (mode.kind === "loading-existing") {
    headerSubtitleParts.push("Looking for existing session…");
  } else {
    headerSubtitleParts.push("No session yet");
  }

  return (
    <div
      className="fixed inset-0 z-50"
      onClick={onClose}
      style={{ background: "oklch(0% 0 0 / 0.22)" }}
    >
      <aside
        className="slide-over flex flex-col bg-white"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(760px, 100vw)" }}
        aria-label="Practice prep"
      >
        {/* Header */}
        <header className="px-5 pt-4 pb-2 border-b border-gray-200 sticky top-0 bg-white shrink-0">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-0.5">
                AI workspace · {subject}
                {linkedAssignment ? (
                  <>
                    {" "}· <span className="text-gray-700">{linkedAssignment.title}</span>
                  </>
                ) : null}
              </div>
              <h3 className="text-lg font-bold leading-tight truncate">
                {session?.title || `${subject} — ${modeMeta.label}`}
              </h3>
              <div className="text-xs text-gray-500 mt-0.5">
                {headerSubtitleParts.join(" · ")}
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
                    🖨 print
                  </button>
                  <button
                    type="button"
                    onClick={copyMarkdown}
                    className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
                    title="Copy this draft as markdown"
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
          </div>

          {/* Mode tabs */}
          <div role="tablist" className="flex items-center gap-1 -mb-px">
            {(["review_prep", "assignment_help", "review_work"] as const).map((k) => {
              const meta = MODE_DEFS[k];
              const isActive = activeKind === k;
              const onlyForReview = k === "review_prep" && linkedAssignment?.kind &&
                linkedAssignment.kind !== "assignment";
              if (onlyForReview) return null;
              return (
                <button
                  key={k}
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActiveKind(k)}
                  className={
                    "px-3 py-2 text-sm font-medium border-b-2 transition-colors " +
                    (isActive
                      ? `border-current ${meta.textCls}`
                      : "border-transparent text-gray-500 hover:text-gray-800")
                  }
                >
                  <span className="mr-1.5">{meta.emoji}</span>
                  {meta.shortLabel}
                </button>
              );
            })}
          </div>
        </header>

        {/* Body */}
        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={
            "flex-1 overflow-auto px-5 py-4 space-y-4 relative " +
            (dragHover ? "ring-4 ring-violet-400 ring-inset bg-violet-50/40" : "")
          }
        >
          {dragHover && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-violet-700 text-lg font-semibold z-10">
              Drop {isCheck ? "the kid's completed work" : "classwork scans"} here
            </div>
          )}

          {errorMsg && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
              {errorMsg}
            </div>
          )}

          {mode.kind === "loading-existing" && (
            <div className="text-sm text-gray-500 italic">Looking for an existing session…</div>
          )}

          {mode.kind === "needs-start" && (
            <StartCard
              meta={modeMeta}
              busy={busy}
              onStart={startNew}
              isCheck={isCheck}
              pendingShots={pendingShots}
              onPickFiles={() => fileInputRef.current?.click()}
              onTakePhoto={() => cameraInputRef.current?.click()}
              onRemoveFromQueue={removeFromQueue}
              onDiscardPending={() => setPendingShots([])}
              pendingPinnedSources={pendingPinnedSources}
              onOpenSourcesPicker={() => setSourcesPickerOpen(true)}
              onRemovePendingSource={(idx) =>
                setPendingPinnedSources((prev) => prev.filter((_, i) => i !== idx))
              }
              startPrompt={startPrompt}
              onStartPromptChange={setStartPrompt}
              activeKind={activeKind}
            />
          )}

          {/* The hidden file inputs need to live OUTSIDE the session-only
              branch so they're available for the StartCard upload too. */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,application/pdf"
            className="hidden"
            onChange={(e) => { queueFiles(e.target.files); e.target.value = ""; }}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => { queueFiles(e.target.files); e.target.value = ""; }}
          />

          {session && (
            <>
              <IterationSwitcher
                session={session}
                activeIterIdx={activeIterIdx}
                onSelect={setActiveIterIdx}
                meta={modeMeta}
              />

              {activeIter && (
                <IterationCard
                  iteration={activeIter}
                  isPreferred={activeIter.id === session.preferred_iteration_id}
                  onStar={() => setPreferred(activeIter.id)}
                  kind={session.kind}
                  meta={modeMeta}
                />
              )}

              <SourcesSection
                pinned={session.pinned_sources || []}
                onOpen={() => setSourcesPickerOpen(true)}
                onRemove={removePinnedSource}
                meta={modeMeta}
              />

              <ScansSection
                scans={session.scans}
                purpose={uploadPurpose}
                pendingShots={pendingShots}
                onPickFiles={() => fileInputRef.current?.click()}
                onTakePhoto={() => cameraInputRef.current?.click()}
                onRemoveFromQueue={removeFromQueue}
                onUploadPending={uploadPending}
                onDiscardPending={() => setPendingShots([])}
                meta={modeMeta}
                isCheck={isCheck}
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

        {/* Footer: refinement input */}
        {session && (
          <footer className="border-t border-gray-200 bg-white px-4 py-3 shrink-0">
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
              {isCheck ? "Refine the review" : "Refine with a prompt"}
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
                  isCheck
                    ? 'e.g. "be gentler" · "estimate the score" · "look at Q3 again" · "in Hindi"'
                    : activeKind === "assignment_help"
                    ? 'e.g. "show a worked example" · "shorter outline" · "in Hindi" · "match scan #1"'
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
                  "px-3 py-1 rounded disabled:opacity-50 self-stretch " + modeMeta.buttonCls
                }
                title="⌘+Enter to send"
              >
                Refine
              </button>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">
              ⌘+Enter to send · drop files anywhere in this panel · iterations cap at 30
            </div>
          </footer>
        )}
      </aside>

      {sourcesPickerOpen && (
        <SourcesPicker
          childId={childId}
          classLevel={childClassLevel}
          subject={subject}
          initial={session?.pinned_sources || pendingPinnedSources}
          onSave={saveSources}
          onClose={() => setSourcesPickerOpen(false)}
        />
      )}
    </div>
  );
}


// ───────────────────────── sub-components ─────────────────────────

function SourcesSection({
  pinned, onOpen, onRemove, meta,
}: {
  pinned: PinnedSource[];
  onOpen: () => void;
  onRemove: (idx: number) => void;
  meta: ModeMeta;
}) {
  return (
    <section className={`border ${meta.ringCls.replace("ring-", "border-").replace("-500", "-200")} rounded-lg ${meta.bgSoft} p-3`}>
      <div className="flex items-center justify-between mb-2 gap-2">
        <h4 className={`text-xs font-semibold uppercase tracking-wider ${meta.textCls}`}>
          📚 Pinned sources · {pinned.length}
        </h4>
        <button
          type="button"
          onClick={onOpen}
          className="text-sm px-3 py-1.5 border border-gray-400 bg-white rounded font-medium hover:bg-gray-50 inline-flex items-center gap-1"
          title="Pin library files, portal resources, or syllabus topics as grounding context"
        >
          📚 <span className="hidden sm:inline">{pinned.length === 0 ? "Add sources" : "Manage"}</span>
        </button>
      </div>
      {pinned.length === 0 ? (
        <p className="text-xs text-gray-600 italic leading-relaxed">
          Pin a textbook from the <strong>Library</strong>, a worksheet from
          portal <strong>Resources</strong>, or specific <strong>Syllabus</strong>
          topics — they ground every iteration's prompt as authoritative
          context.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {pinned.map((p, i) => (
            <span
              key={`${p.type}-${p.ref}`}
              className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border border-gray-300 bg-white"
              title={`${p.type} · ${p.ref}`}
            >
              <span className="opacity-60">
                {p.type === "library" ? "📚" : p.type === "resource" ? "📁" : "🎯"}
              </span>
              <span className="max-w-[180px] truncate">{p.label}</span>
              <button
                onClick={() => onRemove(i)}
                className="text-rose-600 hover:text-rose-800 ml-0.5"
                aria-label={`Unpin ${p.label}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}




function StartCard({
  meta, busy, onStart, isCheck,
  pendingShots, onPickFiles, onTakePhoto, onRemoveFromQueue, onDiscardPending,
  pendingPinnedSources, onOpenSourcesPicker, onRemovePendingSource,
  startPrompt, onStartPromptChange, activeKind,
}: {
  meta: ModeMeta;
  busy: string | null;
  onStart: () => void;
  isCheck: boolean;
  pendingShots: File[];
  onPickFiles: () => void;
  onTakePhoto: () => void;
  onRemoveFromQueue: (idx: number) => void;
  onDiscardPending: () => void;
  pendingPinnedSources: PinnedSource[];
  onOpenSourcesPicker: () => void;
  onRemovePendingSource: (idx: number) => void;
  startPrompt: string;
  onStartPromptChange: (v: string) => void;
  activeKind: PracticeKind;
}) {
  const hasShots = pendingShots.length > 0;
  const hasSources = pendingPinnedSources.length > 0;
  const hasUserPrompt = startPrompt.trim().length > 0;
  const ctaParts: string[] = [];
  if (hasShots) {
    ctaParts.push(`${pendingShots.length} ${pendingShots.length === 1 ? "file" : "files"}`);
  }
  if (hasSources) {
    ctaParts.push(`${pendingPinnedSources.length} source${pendingPinnedSources.length === 1 ? "" : "s"}`);
  }
  if (hasUserPrompt) {
    ctaParts.push("your prompt");
  }
  const ctaCopy = ctaParts.length > 0
    ? `${isCheck ? "Review" : "Generate"} with ${ctaParts.join(" + ")}`
    : isCheck
    ? "Generate review (no uploads yet)"
    : meta.ctaCopy;

  const promptPlaceholder =
    activeKind === "review_work"
      ? "e.g. \"the kid struggles with carrying — flag carry errors specifically\" · \"be gentle, this was a tough topic\""
      : activeKind === "assignment_help"
      ? "e.g. \"give me a 4-paragraph outline\" · \"focus on the analogy method\" · \"in Hindi\""
      : "e.g. \"focus on word problems\" · \"include 2 HOTS questions\" · \"mix Sanskrit + Hindi\"";

  return (
    <div className={`${meta.bgSoft} border border-gray-200 rounded-lg p-4 text-sm space-y-4`}>
      <div className={`text-base font-semibold ${meta.textCls} flex items-center gap-2`}>
        <span className="text-xl">{meta.emoji}</span> {meta.label}
      </div>
      <p className="text-gray-700 leading-relaxed">{meta.introHelp}</p>

      {/* Pinned-sources block — usable in every mode, so the parent can
          ground the FIRST iteration on textbooks / resources / specific
          topics without first having to create+iterate empty. */}
      <div className="bg-white border-2 border-dashed border-gray-300 rounded-lg p-3">
        <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
          <div className="text-xs font-semibold uppercase tracking-wider text-gray-600">
            📚 Optional — pin grounding sources
          </div>
          <button
            type="button"
            onClick={onOpenSourcesPicker}
            className="text-sm px-3 py-1.5 border border-gray-400 bg-white rounded font-medium hover:bg-gray-50 inline-flex items-center gap-1"
            title="Pin library files, portal resources, or syllabus topics"
          >
            📚 <span className="hidden sm:inline">{hasSources ? "Manage" : "Add sources"}</span>
          </button>
        </div>
        {hasSources ? (
          <div className="flex flex-wrap gap-1.5">
            {pendingPinnedSources.map((p, i) => (
              <span
                key={`${p.type}-${p.ref}-${i}`}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border border-gray-300 bg-white"
                title={`${p.type} · ${p.ref}`}
              >
                <span className="opacity-60">
                  {p.type === "library" ? "📚" : p.type === "resource" ? "📁" : "🎯"}
                </span>
                <span className="max-w-[180px] truncate">{p.label}</span>
                <button
                  onClick={() => onRemovePendingSource(i)}
                  className="text-rose-600 hover:text-rose-800 ml-0.5"
                  aria-label={`Remove ${p.label}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-500 italic leading-relaxed">
            Pin a textbook from <strong>Library</strong>, a worksheet from
            portal <strong>Resources</strong>, or specific
            <strong> Syllabus</strong> topics — they ground every iteration.
          </p>
        )}
      </div>

      {/* Big upload bar — visible BEFORE session creation so the
          parent can queue scans and have them included in the first
          generation. */}
      <div className="bg-white border-2 border-dashed border-gray-300 rounded-lg p-3">
        <div className="text-xs font-semibold uppercase tracking-wider text-gray-600 mb-2">
          {isCheck ? "📷 Upload the kid's completed work" : "📎 Optional — upload classwork scans"}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onTakePhoto}
            className="text-sm px-3 py-2 border border-gray-400 bg-white rounded font-medium hover:bg-gray-50 inline-flex items-center gap-1.5"
            title="Open camera (mobile) for a photo"
          >
            📷 Take photo
          </button>
          <button
            type="button"
            onClick={onPickFiles}
            className="text-sm px-3 py-2 border border-gray-400 bg-white rounded font-medium hover:bg-gray-50 inline-flex items-center gap-1.5"
            title="Pick files from device"
          >
            📁 Choose files
          </button>
          <span className="text-xs text-gray-500 self-center">
            (or drag-drop anywhere in this panel · multiple files OK)
          </span>
        </div>

        {hasShots && (
          <div className="mt-3 space-y-2">
            <div className="text-[11px] text-gray-700 font-medium flex items-center justify-between">
              <span>Queued · {pendingShots.length} {pendingShots.length === 1 ? "file" : "files"}</span>
              <button
                type="button"
                onClick={onDiscardPending}
                className="text-[10px] text-rose-700 hover:underline"
              >
                clear queue
              </button>
            </div>
            <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5">
              {pendingShots.map((f, i) => (
                <PendingThumb key={i} file={f} onRemove={() => onRemoveFromQueue(i)} />
              ))}
            </div>
          </div>
        )}
      </div>

      {isCheck && !hasShots && (
        <p className="text-xs text-gray-500 leading-relaxed bg-amber-50 border border-amber-200 rounded p-2">
          💡 <strong>Tip</strong>: take photos of the completed pages first.
          The review without uploads is just a placeholder — Claude needs
          the kid's actual work to give per-question feedback.
        </p>
      )}

      {/* Optional initial prompt — combines with our auto-scaffolding
          for the first round so the parent can steer round one without
          losing the grounding hints we already inject. Available in
          every mode. */}
      <div className="bg-white border-2 border-dashed border-gray-300 rounded-lg p-3">
        <label className="text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1.5 block">
          ✏️ Your instructions for round 1 (optional)
        </label>
        <textarea
          rows={2}
          value={startPrompt}
          onChange={(e) => onStartPromptChange(e.target.value)}
          placeholder={promptPlaceholder}
          className="w-full text-sm border border-gray-300 rounded px-2 py-1.5 resize-none"
        />
        <div className="text-[10px] text-gray-400 mt-1 leading-snug">
          Combines with the default scaffolding (mode-specific instructions
          + grounding hints) — your prompt steers round 1 without losing
          context. You can always iterate again from the chat box at the
          bottom.
        </div>
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={onStart}
          disabled={busy !== null}
          className={`flex-1 px-3.5 py-2.5 rounded font-medium text-sm disabled:opacity-60 ${meta.buttonCls}`}
        >
          {busy ?? ctaCopy}
        </button>
      </div>
    </div>
  );
}

function IterationSwitcher({
  session, activeIterIdx, onSelect, meta,
}: {
  session: PracticeSessionOut;
  activeIterIdx: number | null;
  onSelect: (idx: number) => void;
  meta: ModeMeta;
}) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] uppercase tracking-wider text-gray-500">Drafts:</span>
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
                ? `border-current ${meta.textCls} ${meta.bgSoft} font-medium`
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
  iteration, isPreferred, onStar, kind, meta,
}: {
  iteration: PracticeIterationOut;
  isPreferred: boolean;
  onStar: () => void;
  kind: PracticeKind;
  meta: ModeMeta;
}) {
  const out = iteration.output_json;
  return (
    <article className="border border-gray-200 rounded-lg bg-white shadow-sm overflow-hidden">
      {iteration.parent_prompt && (
        <div className={`px-3 py-2 border-b border-gray-100 text-xs text-gray-700 ${meta.bgSoft}`}>
          <span className={`text-[10px] uppercase tracking-wider mr-1.5 ${meta.textCls}`}>
            Prompt
          </span>
          {iteration.parent_prompt}
        </div>
      )}

      <div className="px-5 py-4 space-y-3">
        {out?.title && (
          <h4 className="text-base font-semibold leading-tight">{out.title}</h4>
        )}

        {kind === "review_prep" && <ReviewBody out={out} fallback={iteration.output_md} />}
        {kind === "assignment_help" && <HelpBody out={out} />}
        {kind === "review_work" && <ReviewWorkBody out={out} />}

        {out?.honest_caveat && (
          <div className="text-[11px] text-gray-500 italic border-t border-gray-100 pt-2">
            {out.honest_caveat}
          </div>
        )}
      </div>

      <div className="px-4 py-2 border-t border-gray-100 flex items-center gap-2 text-xs text-gray-500 bg-gray-50">
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

function ReviewBody({ out, fallback }: { out: PracticeOutputJson | null; fallback: string }) {
  if (!out || !Array.isArray(out.questions)) {
    return <pre className="text-sm leading-relaxed whitespace-pre-wrap font-sans">{fallback}</pre>;
  }
  const totalMarks = out.questions.reduce((s, q) => s + (q.marks || 0), 0);
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
                <span className="ml-2 text-xs text-gray-500 font-normal">({q.marks} marks)</span>
              ) : null}
            </div>
            {q.topic_ref && <div className="text-[11px] text-gray-500 mt-0.5">↳ {q.topic_ref}</div>}
            {q.expected_answer && (
              <details className="mt-1 text-xs text-gray-600">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-800">
                  show expected answer
                </summary>
                <div className="mt-1 pl-2 border-l-2 border-gray-200">
                  {q.expected_answer}
                  {q.expected_solution_md && (
                    <pre className="whitespace-pre-wrap font-sans mt-1">{q.expected_solution_md}</pre>
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

function HelpBody({ out }: { out: PracticeOutputJson | null }) {
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
      {out.summary && <p className="text-sm text-gray-700 italic">{out.summary}</p>}
      {out.format && (
        <div className="text-xs">
          <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
            format · {out.format}
          </span>
        </div>
      )}
      <div className="space-y-3">
        {out.sections.map((s: PracticeHelpSection, i: number) => (
          <section key={i} className={"border rounded p-3 " + sectionToneCls(s.kind)}>
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

function ReviewWorkBody({ out }: { out: PracticeOutputJson | null }) {
  if (!out) return <div className="text-sm text-gray-500 italic">No review yet.</div>;
  const items = out.by_question || [];
  return (
    <>
      {out.overall_assessment && (
        <p className="text-sm text-gray-800 leading-relaxed bg-gray-50 border-l-4 border-emerald-400 p-2 pl-3">
          {out.overall_assessment}
        </p>
      )}
      {out.estimated_score && (
        <ScoreBadge score={out.estimated_score} />
      )}
      {items.length > 0 && (
        <div className="space-y-2">
          {items.map((q: ReviewWorkItem, i: number) => (
            <ReviewWorkRow key={i} q={q} />
          ))}
        </div>
      )}
      {out.general_suggestions && out.general_suggestions.length > 0 && (
        <section className="border border-blue-200 rounded p-3 bg-blue-50/40">
          <h5 className="text-sm font-semibold mb-1 text-blue-900">General suggestions</h5>
          <ul className="text-sm space-y-0.5 list-disc pl-5">
            {out.general_suggestions.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </section>
      )}
    </>
  );
}

function ScoreBadge({ score }: { score: { value: number; max: number; confidence: string } }) {
  const pct = score.max > 0 ? (score.value / score.max) * 100 : 0;
  const tone =
    pct >= 85 ? "emerald" : pct >= 70 ? "amber" : pct >= 50 ? "orange" : "rose";
  const cls = {
    emerald: "bg-emerald-50 border-emerald-300 text-emerald-900",
    amber:   "bg-amber-50 border-amber-300 text-amber-900",
    orange:  "bg-orange-50 border-orange-300 text-orange-900",
    rose:    "bg-rose-50 border-rose-300 text-rose-900",
  }[tone];
  return (
    <div className={`inline-flex items-center gap-3 border rounded-lg px-3 py-2 ${cls}`}>
      <div className="text-2xl font-bold leading-none">
        {score.value}<span className="text-sm font-medium opacity-60">/{score.max}</span>
      </div>
      <div className="text-xs leading-tight">
        <div className="font-semibold">Estimated score</div>
        <div className="opacity-70">{pct.toFixed(0)}% · {score.confidence} confidence</div>
      </div>
    </div>
  );
}

function ReviewWorkRow({ q }: { q: ReviewWorkItem }) {
  const tone = verdictTone(q.verdict);
  return (
    <div className={`border rounded-md p-2.5 ${tone.bg} ${tone.border}`}>
      <div className="flex items-baseline gap-2 mb-1">
        <span className={`text-xs font-bold ${tone.text}`}>{tone.icon}</span>
        <span className="text-sm font-semibold">{q.ref}</span>
        <span className={`text-[10px] uppercase tracking-wider ${tone.text} opacity-80`}>
          {q.verdict.replace("_", " ")}
        </span>
      </div>
      {q.what_kid_did && (
        <div className="text-xs text-gray-600 italic mb-1">
          <span className="opacity-60">Kid wrote: </span>"{q.what_kid_did}"
        </div>
      )}
      <div className="text-sm text-gray-800 leading-snug">{q.feedback}</div>
      {q.suggestion && (
        <div className="text-xs text-gray-700 mt-1.5 pl-2 border-l-2 border-gray-300">
          <span className="font-medium">Try:</span> {q.suggestion}
        </div>
      )}
    </div>
  );
}

function verdictTone(v: ReviewWorkVerdict) {
  switch (v) {
    case "correct":
      return { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", icon: "✅" };
    case "partially_correct":
      return { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", icon: "🟡" };
    case "incorrect":
      return { bg: "bg-rose-50", border: "border-rose-200", text: "text-rose-700", icon: "❌" };
    default:
      return { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: "❓" };
  }
}

function ScansSection({
  scans, purpose, pendingShots, onPickFiles, onTakePhoto,
  onRemoveFromQueue, onUploadPending, onDiscardPending, meta, isCheck,
}: {
  scans: PracticeClassworkScanOut[];
  purpose: ScanPurpose;
  pendingShots: File[];
  onPickFiles: () => void;
  onTakePhoto: () => void;
  onRemoveFromQueue: (idx: number) => void;
  onUploadPending: () => void;
  onDiscardPending: () => void;
  meta: ModeMeta;
  isCheck: boolean;
}) {
  // Filter scans to ones that match the active mode's purpose. Show
  // both kinds if there's a mix (so the parent doesn't lose track of a
  // scan they uploaded under a different mode).
  const matching = scans.filter((s) => s.purpose === purpose);
  const otherKind = scans.filter((s) => s.purpose !== purpose);

  const headingLabel = isCheck
    ? "📷 Kid's completed work"
    : "📎 Classwork reference scans";

  return (
    <section className={`border ${meta.ringCls.replace("ring-", "border-").replace("-500", "-200")} rounded-lg ${meta.bgSoft} p-3`}>
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <h4 className={`text-xs font-semibold uppercase tracking-wider ${meta.textCls}`}>
          {headingLabel} · {matching.length}
        </h4>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onTakePhoto}
            className="text-sm px-3 py-1.5 border border-gray-400 bg-white rounded font-medium hover:bg-gray-50 inline-flex items-center gap-1"
            title="Open camera (mobile) for a photo"
          >
            📷 <span className="hidden sm:inline">Take photo</span>
          </button>
          <button
            type="button"
            onClick={onPickFiles}
            className="text-sm px-3 py-1.5 border border-gray-400 bg-white rounded font-medium hover:bg-gray-50 inline-flex items-center gap-1"
            title="Pick files from device"
          >
            📁 <span className="hidden sm:inline">Choose files</span>
          </button>
        </div>
      </div>

      {/* Pending shot queue — preview before upload */}
      {pendingShots.length > 0 && (
        <div className="mb-3 p-2 bg-white border border-amber-300 rounded space-y-2">
          <div className="text-[11px] text-amber-900 font-medium flex items-center justify-between">
            <span>Queued · {pendingShots.length} file{pendingShots.length === 1 ? "" : "s"}</span>
            <span className="text-[10px] text-gray-500">Tap a thumbnail to remove</span>
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {pendingShots.map((f, i) => (
              <PendingThumb key={i} file={f} onRemove={() => onRemoveFromQueue(i)} />
            ))}
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onUploadPending}
              className={`text-xs px-2.5 py-1 rounded ${meta.buttonCls}`}
            >
              Upload {pendingShots.length} + extract
            </button>
            <button
              type="button"
              onClick={onDiscardPending}
              className="text-xs px-2.5 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
            >
              Discard queue
            </button>
            <button
              type="button"
              onClick={onTakePhoto}
              className="text-xs px-2.5 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50 ml-auto"
            >
              📷 Another
            </button>
          </div>
        </div>
      )}

      {/* Existing uploaded scans */}
      {matching.length === 0 ? (
        <p className="text-xs text-gray-600 italic leading-relaxed">
          {isCheck ? (
            <>Take photos of the kid's completed pages. Multiple shots OK — they all become grounding for the LLM review. <strong>📷 Take photo</strong> opens the camera on mobile; on desktop, drag-drop files anywhere in this panel.</>
          ) : (
            <>Drop or pick photos / PDFs of recent classwork — notebook pages, blackboard photos, worksheets — and the next iteration uses them as grounding for what's been covered.</>
          )}
        </p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {matching.map((s) => (
            <ScanTile key={s.id} scan={s} />
          ))}
        </div>
      )}

      {otherKind.length > 0 && (
        <div className="mt-3 text-[11px] text-gray-500 italic">
          {otherKind.length} other scan{otherKind.length === 1 ? "" : "s"} bound to this session
          (different purpose) — switch to the matching tab to view.
        </div>
      )}
    </section>
  );
}

function PendingThumb({ file, onRemove }: { file: File; onRemove: () => void }) {
  const url = useObjectUrl(file);
  const isImage = file.type.startsWith("image/");
  return (
    <button
      type="button"
      onClick={onRemove}
      className="relative aspect-square rounded border border-amber-200 bg-white overflow-hidden hover:opacity-70"
      title={`${file.name} — click to remove`}
    >
      {isImage ? (
        <img src={url} alt={file.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-2xl text-gray-400">📄</div>
      )}
      <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[9px] px-1 py-0.5 truncate">
        {file.name}
      </div>
      <div className="absolute top-0 right-0 bg-rose-600 text-white text-[10px] w-4 h-4 leading-4 text-center">
        ×
      </div>
    </button>
  );
}

function ScanTile({ scan }: { scan: PracticeClassworkScanOut }) {
  const isPdf = !scan.extracted_summary && scan.extracted_at == null;
  const url = api.practiceScanThumbnailUrl(scan.id);
  return (
    <div className="border border-gray-200 rounded bg-white overflow-hidden flex flex-col">
      <div className="aspect-[4/3] bg-gray-100 flex items-center justify-center overflow-hidden">
        {isPdf ? (
          <span className="text-3xl text-gray-400">📄</span>
        ) : (
          <img
            src={url}
            alt={`Scan ${scan.id}`}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        )}
      </div>
      <div className="px-2 py-1.5 text-[11px] flex-1">
        <div className="font-semibold text-gray-700 mb-0.5 flex items-center gap-1">
          <span>#{scan.id}</span>
          <span className="text-gray-400 font-normal text-[10px]">
            · {new Date(scan.uploaded_at || "").toLocaleDateString()}
          </span>
        </div>
        {scan.extracted_summary ? (
          <div className="text-gray-700 leading-snug" title={scan.extracted_summary}>
            {scan.extracted_summary.length > 80
              ? scan.extracted_summary.slice(0, 78) + "…"
              : scan.extracted_summary}
          </div>
        ) : (
          <div className="text-gray-400 italic">
            {scan.extracted_at ? "no summary" : "extracting…"}
          </div>
        )}
        {scan.extracted_topics && scan.extracted_topics.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-0.5">
            {scan.extracted_topics.slice(0, 3).map((t) => (
              <span
                key={t}
                className="text-[9px] px-1 rounded-full bg-violet-100 text-violet-800"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Lifecycle-tracked object URL for a File so the Pending preview shows
// without leaking memory.
function useObjectUrl(file: File): string {
  const [url, setUrl] = useState<string>("");
  useEffect(() => {
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return url;
}


// ───────────────────────── print window ─────────────────────────

function openPrintWindow(session: PracticeSessionOut, iteration: PracticeIterationOut) {
  const w = window.open("", "_blank", "width=900,height=1100");
  if (!w) return;
  const out = iteration.output_json;
  const safe = (s: string) =>
    s.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]!));

  let body = "";
  if (session.kind === "review_work" && out?.by_question) {
    const score = out.estimated_score;
    body = `
      ${out.overall_assessment ? `<p class="lede">${safe(out.overall_assessment)}</p>` : ""}
      ${score ? `<div class="score">Estimated: <strong>${score.value}/${score.max}</strong> (${score.confidence})</div>` : ""}
      ${out.by_question.map((q) => `
        <section>
          <h2>${safe(q.ref)} <span class="tag">${safe(q.verdict)}</span></h2>
          ${q.what_kid_did ? `<div class="kid">Kid wrote: "${safe(q.what_kid_did)}"</div>` : ""}
          <div>${safe(q.feedback)}</div>
          ${q.suggestion ? `<div class="sug">Try: ${safe(q.suggestion)}</div>` : ""}
        </section>`).join("")}
      ${out.general_suggestions && out.general_suggestions.length > 0 ? `
        <section><h2>General suggestions</h2><ul>${out.general_suggestions.map((g) => `<li>${safe(g)}</li>`).join("")}</ul></section>` : ""}
    `;
  } else if (session.kind === "assignment_help" && out?.sections) {
    body = `
      ${out.summary ? `<p class="lede">${safe(out.summary)}</p>` : ""}
      ${out.sections.map((s) => `
        <section>
          <h2>${safe(s.heading)}${s.kind ? ` <span class="tag">${safe(s.kind)}</span>` : ""}</h2>
          <pre>${safe(s.body_md)}</pre>
        </section>`).join("")}
      ${out.next_steps && out.next_steps.length > 0
        ? `<section><h2>Next steps</h2><ul>${out.next_steps.map((n) => `<li>${safe(n)}</li>`).join("")}</ul></section>`
        : ""}
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
      ${out.answer_key
        ? `<section class="answers"><h2>Answer key</h2><pre>${safe(out.answer_key)}</pre></section>`
        : ""}
    `;
  }

  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${safe(out?.title || session.title)}</title>
    <style>
      body { font: 14px/1.55 -apple-system, "Segoe UI", system-ui, sans-serif; max-width: 720px; margin: 24px auto; padding: 0 24px; color: #111; }
      h1 { font-size: 22px; margin: 0 0 4px; }
      .meta { color: #666; font-size: 13px; margin-bottom: 16px; border-bottom: 1px solid #ddd; padding-bottom: 12px; }
      h2 { font-size: 15px; margin: 18px 0 6px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 3px; }
      .tag { font-size: 11px; color: #888; font-weight: 400; text-transform: uppercase; letter-spacing: 0.04em; margin-left: 6px; }
      pre { white-space: pre-wrap; font-family: inherit; margin: 0 0 8px; }
      .lede { color: #333; font-size: 14px; }
      .kid { color: #666; font-size: 12px; font-style: italic; margin-bottom: 4px; }
      .sug { color: #555; font-size: 12px; margin-top: 6px; padding-left: 10px; border-left: 2px solid #aaa; }
      .score { font-size: 14px; padding: 6px 10px; background: #f3f4f6; border-radius: 4px; margin-bottom: 12px; display: inline-block; }
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
    <div class="meta">${safe(session.subject)} · ${session.kind} · iteration #${iteration.iteration_index}</div>
    ${body}
    ${out?.honest_caveat ? `<div class="caveat">${safe(out.honest_caveat)}</div>` : ""}
  </body></html>`);
  w.document.close();
}
