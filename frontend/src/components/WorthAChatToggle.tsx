/**
 * WorthAChatToggle — single-row worth-a-chat control for the audit drawer.
 *
 * If unflagged: a small "Mark for next PTM" button.
 * If flagged: chip + inline-editable reason + clear button.
 *
 * Shares the inline-edit pattern with WorthAChatTray so the
 * interaction is the same wherever the parent edits a reason.
 */
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Assignment } from "../api";
import { useOptimisticPatch } from "./useOptimisticPatch";

export function WorthAChatToggle({ a }: { a: Assignment }) {
  const qc = useQueryClient();
  const optimisticPatch = useOptimisticPatch();
  const flagged = !!a.discuss_with_teacher_at;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(a.discuss_with_teacher_note || "");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!editing) setDraft(a.discuss_with_teacher_note || "");
  }, [a.discuss_with_teacher_note, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const flag = async () => {
    await optimisticPatch(
      a.id,
      { discuss_with_teacher: true },
      { label: "Flagged for PTM chat" },
    );
    qc.invalidateQueries({ queryKey: ["worth-a-chat"] });
    setEditing(true); // Open inline edit so the parent can add a reason now.
  };

  const clear = async () => {
    await optimisticPatch(
      a.id,
      { discuss_with_teacher: false },
      { label: "Cleared from PTM list" },
    );
    qc.invalidateQueries({ queryKey: ["worth-a-chat"] });
  };

  const saveNote = async () => {
    const next = draft.trim() || null;
    await optimisticPatch(
      a.id,
      { discuss_with_teacher_note: next },
      { label: "Reason updated" },
    );
    qc.invalidateQueries({ queryKey: ["worth-a-chat"] });
    setEditing(false);
  };

  if (!flagged) {
    return (
      <button
        type="button"
        onClick={flag}
        className="text-xs px-2 py-1 rounded border border-violet-200 text-violet-800 bg-violet-50/40 hover:bg-violet-50 inline-flex items-center gap-1"
        title="Add this to the next PTM brief"
      >
        💬 Mark for next PTM
      </button>
    );
  }

  return (
    <div className="text-xs px-2 py-1 rounded border border-violet-200 bg-violet-50/60 flex items-baseline gap-2 flex-wrap">
      <span className="font-medium text-violet-900">💬 worth a chat</span>
      {editing ? (
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Enter") saveNote();
            if (e.key === "Escape") {
              setDraft(a.discuss_with_teacher_note || "");
              setEditing(false);
            }
          }}
          onBlur={saveNote}
          placeholder="reason for chat"
          className="flex-1 min-w-[160px] border border-violet-300 rounded px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-violet-200"
        />
      ) : a.discuss_with_teacher_note ? (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-violet-900 hover:underline text-left flex-1 truncate"
          title="Click to edit"
        >
          ↳ {a.discuss_with_teacher_note}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-violet-700 hover:underline italic"
        >
          + add reason
        </button>
      )}
      <button
        type="button"
        onClick={clear}
        className="text-gray-400 hover:text-red-700 ml-auto"
        title="Unflag"
      >
        ✕
      </button>
    </div>
  );
}
