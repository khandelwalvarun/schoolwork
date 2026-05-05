/**
 * WorthAChatTray — items the parent flagged for the next PTM.
 *
 * Built on the shared Tray primitive (components/Tray.tsx). Tray
 * handles header chrome, expand/collapse defaults, and tone vocab —
 * leaving this file responsible for one thing: how to render a
 * worth-a-chat row with an inline-editable reason.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Assignment, api } from "../api";
import { formatDate } from "../util/dates";
import { useOptimisticPatch } from "./useOptimisticPatch";
import { Tray, trayLineClass } from "./Tray";

export function WorthAChatTray({
  childId,
  onOpenAudit,
}: {
  childId: number;
  onOpenAudit?: (a: Assignment) => void;
}) {
  const qc = useQueryClient();
  const optimisticPatch = useOptimisticPatch();
  const { data, isLoading } = useQuery({
    queryKey: ["worth-a-chat", childId],
    queryFn: () => api.worthAChat(childId),
    refetchInterval: 30_000,
  });

  if (isLoading) return null;
  if (!data || data.length === 0) return null;

  const setNote = async (a: Assignment, next: string | null) => {
    await optimisticPatch(
      a.id,
      { discuss_with_teacher_note: next },
      { label: "Reason updated" },
    );
    qc.invalidateQueries({ queryKey: ["worth-a-chat"] });
  };

  const clearFlag = async (a: Assignment) => {
    await optimisticPatch(
      a.id,
      { discuss_with_teacher: false },
      { label: "Cleared from PTM list" },
    );
    qc.invalidateQueries({ queryKey: ["worth-a-chat"] });
  };

  return (
    <Tray
      title="💬 Worth a chat at PTM"
      count={data.length}
      summary={`click to ${data.length === 1 ? "see it" : "review"}`}
      tone="violet"
    >
      <ul className="space-y-0.5">
        {data.map((a) => (
          <PTMLine
            key={a.id}
            a={a}
            onOpen={() => onOpenAudit && onOpenAudit(a)}
            onSetNote={(next) => setNote(a, next)}
            onClear={() => clearFlag(a)}
          />
        ))}
      </ul>
    </Tray>
  );
}

function PTMLine({
  a,
  onOpen,
  onSetNote,
  onClear,
}: {
  a: Assignment;
  onOpen: () => void;
  onSetNote: (next: string | null) => void | Promise<void>;
  onClear: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(a.discuss_with_teacher_note || "");
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Sync draft if the upstream note changes (e.g. from the audit
  // drawer's StatusPopover).
  useEffect(() => {
    if (!editing) setDraft(a.discuss_with_teacher_note || "");
  }, [a.discuss_with_teacher_note, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    const next = draft.trim();
    onSetNote(next || null);
    setEditing(false);
  };
  const cancel = () => {
    setDraft(a.discuss_with_teacher_note || "");
    setEditing(false);
  };

  return (
    <li className={trayLineClass("violet") + " flex items-baseline gap-2 flex-wrap"}>
      <button
        type="button"
        onClick={onOpen}
        className="text-left flex items-baseline gap-2 min-w-0 hover:text-blue-700"
      >
        <span className="text-gray-600 text-xs">{a.subject}</span>
        <span className="font-medium truncate max-w-[18rem]">
          {a.title_en || a.title || "(untitled)"}
        </span>
        {a.due_or_date && (
          <span className="text-xs text-gray-500 whitespace-nowrap">
            {formatDate(a.due_or_date)}
          </span>
        )}
      </button>
      {editing ? (
        <div className="flex items-baseline gap-1 flex-1 min-w-[180px]">
          <span className="text-violet-700">↳</span>
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancel();
            }}
            onBlur={save}
            placeholder="reason for chat"
            className="flex-1 text-xs border border-violet-300 rounded px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-violet-200"
          />
        </div>
      ) : a.discuss_with_teacher_note ? (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-xs text-violet-900 hover:underline text-left truncate min-w-[80px] flex-1"
          title="Click to edit reason"
        >
          ↳ {a.discuss_with_teacher_note}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-xs text-violet-700 hover:underline italic"
        >
          + add reason
        </button>
      )}
      <button
        type="button"
        onClick={onClear}
        className="text-xs text-gray-400 hover:text-red-700 ml-auto"
        title="Remove from PTM list"
      >
        ✕
      </button>
    </li>
  );
}
