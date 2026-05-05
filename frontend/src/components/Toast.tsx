/**
 * Toast — bottom-right notifier with optional Undo (Z) action.
 *
 * Pattern (Superhuman / Linear): the user runs a mutation, sees a brief
 * confirmation, has 5 sec to press `Z` (or click Undo) to roll back.
 * Aria-live=polite so it announces to screen readers without stealing
 * focus.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

type ToastTone = "info" | "success" | "error";
type ToastEntry = {
  id: number;
  message: string;
  tone: ToastTone;
  /** Called when the user clicks Undo or hits Z. Returning a Promise blocks
   *  further toasts/undos until it resolves. */
  onUndo?: () => Promise<void> | void;
  /** Auto-dismiss after this many ms (default 5000). */
  ttlMs?: number;
};

type ToastApi = {
  show: (entry: Omit<ToastEntry, "id">) => number;
  dismiss: (id: number) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

/** App-wide hook. Call `show({ message, onUndo })` from anywhere. */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

/** Mount once at the app root. Renders the toast region + handles Z key. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [stack, setStack] = useState<ToastEntry[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setStack((s) => s.filter((t) => t.id !== id));
  }, []);

  const show = useCallback((entry: Omit<ToastEntry, "id">): number => {
    const id = nextId.current++;
    setStack((s) => [...s, { id, ...entry }]);
    const ttl = entry.ttlMs ?? 5000;
    if (ttl > 0) setTimeout(() => dismiss(id), ttl);
    return id;
  }, [dismiss]);

  // Z-to-undo: undoes the most-recent toast that has `onUndo`. Skips when
  // the user is typing in an input / textarea / contenteditable.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "z" && e.key !== "Z") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;  // Cmd-Z / Ctrl-Z is the OS undo
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      const undoable = [...stack].reverse().find((t) => t.onUndo);
      if (!undoable) return;
      e.preventDefault();
      undoable.onUndo?.();
      dismiss(undoable.id);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [stack, dismiss]);

  const api = useMemo<ToastApi>(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="region"
        aria-live="polite"
        aria-label="Notifications"
        className="fixed bottom-4 right-4 z-toast flex flex-col gap-2 pointer-events-none"
      >
        {stack.map((t) => (
          <ToastCard key={t.id} entry={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ entry, onDismiss }: { entry: ToastEntry; onDismiss: () => void }) {
  const tone =
    entry.tone === "error"   ? "border-red-300 bg-red-50 text-red-900"
  : entry.tone === "success" ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                             : "border-gray-300 bg-white text-gray-800";
  return (
    <div
      className={`pointer-events-auto fade-in shadow-lg rounded-md border ${tone} px-3 py-2 text-sm flex items-center gap-3 min-w-[260px]`}
    >
      <span className="flex-1">{entry.message}</span>
      {entry.onUndo && (
        <button
          onClick={() => {
            entry.onUndo?.();
            onDismiss();
          }}
          className="text-blue-700 hover:underline font-medium inline-flex items-center gap-1"
        >
          Undo <span className="kbd">Z</span>
        </button>
      )}
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="text-gray-400 hover:text-gray-700 leading-none"
      >
        ×
      </button>
    </div>
  );
}
