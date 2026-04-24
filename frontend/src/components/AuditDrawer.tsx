import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, Assignment, StatusHistoryEntry } from "../api";
import Attachments from "./Attachments";
import StatusPopover, { EffectiveStatusChip } from "./StatusPopover";
import { formatDate, formatDateTime, formatDDMMMYYTime } from "../util/dates";

function formatValue(field: string, v: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  if (field === "tags") {
    try {
      const arr = JSON.parse(v);
      return Array.isArray(arr) && arr.length > 0 ? arr.join(", ") : "—";
    } catch {
      return v;
    }
  }
  return v;
}

const FIELD_LABEL: Record<string, string> = {
  parent_status: "Parent status",
  priority: "Priority",
  snooze_until: "Snooze until",
  status_notes: "Notes",
  tags: "Tags",
  portal_status: "Portal status",
};

export default function AuditDrawer({
  a,
  onClose,
}: {
  a: Assignment;
  onClose: () => void;
}) {
  const { data: history } = useQuery({
    queryKey: ["history", a.id],
    queryFn: () => api.assignmentHistory(a.id),
  });
  const editBtnRef = useRef<HTMLButtonElement | null>(null);
  const [popover, setPopover] = useState<DOMRect | null>(null);

  useEffect(() => {
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex" style={{ background: "rgba(0,0,0,0.3)" }} onClick={onClose}>
      <div
        className="ml-auto w-[540px] h-full bg-white shadow-2xl overflow-y-auto slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-gray-200 sticky top-0 bg-white flex items-baseline justify-between">
          <div>
            <div className="text-xs text-gray-500">{a.subject}</div>
            <h3 className="text-lg font-bold">{a.title}</h3>
            {a.title_en && a.title_en !== a.title && (
              <div className="text-sm text-gray-600 italic">→ {a.title_en}</div>
            )}
            <div className="text-xs text-gray-500 mt-1">
              due {formatDate(a.due_or_date)} · portal: <b>{a.portal_status || "pending"}</b>
              {a.parent_status && <> · parent: <b>{a.parent_status}</b></>}
              {a.priority > 0 && <> · priority: {"★".repeat(a.priority)}</>}
              {a.snooze_until && <> · snoozed until {a.snooze_until}</>}
            </div>
            {a.first_seen_at && (
              <div className="text-xs text-gray-500 mt-1" title={a.first_seen_at}>
                First detected by scraper: <b className="font-mono">{formatDDMMMYYTime(a.first_seen_at)}</b>
                {a.last_seen_at && a.last_seen_at !== a.first_seen_at && (
                  <> · last seen <span className="font-mono">{formatDDMMMYYTime(a.last_seen_at)}</span></>
                )}
              </div>
            )}
            <div className="flex items-center gap-2 mt-2">
              <EffectiveStatusChip a={a} />
              <button
                ref={editBtnRef}
                onClick={(e) => {
                  e.stopPropagation();
                  const r = (editBtnRef.current as HTMLButtonElement).getBoundingClientRect();
                  setPopover(r);
                }}
                className="text-xs px-2 py-0.5 border border-blue-300 rounded text-blue-700 hover:bg-blue-50"
              >
                Edit status
              </button>
            </div>
          </div>
          <button onClick={onClose} className="text-2xl text-gray-400 hover:text-gray-700 leading-none">×</button>
        </div>

        <div className="px-5 py-4 space-y-5">
          {a.syllabus_context && (
            <section>
              <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Syllabus</div>
              <div className="text-sm text-purple-800">↳ {a.syllabus_context}</div>
            </section>
          )}

          {a.tags.length > 0 && (
            <section>
              <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Tags</div>
              <div className="flex flex-wrap gap-1">
                {a.tags.map((t) => (
                  <span key={t} className="px-2 py-0.5 rounded-full border border-blue-200 bg-blue-50 text-blue-800 text-xs">
                    {t}
                  </span>
                ))}
              </div>
            </section>
          )}

          {a.status_notes && (
            <section>
              <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Notes</div>
              <div className="text-sm whitespace-pre-wrap">{a.status_notes}</div>
            </section>
          )}

          {a.attachments && a.attachments.length > 0 && (
            <section>
              <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Attachments</div>
              <Attachments items={a.attachments} />
            </section>
          )}

          <section>
            <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Status timeline</div>
            {!history && <div className="text-gray-500 text-sm">Loading…</div>}
            {history && history.length === 0 && (
              <div className="text-gray-500 text-sm">No state changes recorded yet.</div>
            )}
            {history && history.length > 0 && (
              <ol className="space-y-2">
                {history.map((h: StatusHistoryEntry) => (
                  <li key={h.id} className="border-l-2 border-gray-200 pl-3 pb-2">
                    <div className="text-xs text-gray-500">
                      {formatDateTime(h.created_at)} ·{" "}
                      <span className="font-medium">{h.source}</span>
                      {h.actor ? ` (${h.actor})` : ""}
                    </div>
                    <div className="text-sm">
                      <b>{FIELD_LABEL[h.field] || h.field}</b>:{" "}
                      <span className="text-gray-500">{formatValue(h.field, h.old_value)}</span>{" → "}
                      <span className="text-gray-900">{formatValue(h.field, h.new_value)}</span>
                    </div>
                    {h.note && <div className="text-xs text-gray-600 italic mt-0.5">“{h.note}”</div>}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>
      {popover && (
        <StatusPopover
          a={a}
          anchorRect={popover}
          onClose={() => setPopover(null)}
        />
      )}
    </div>
  );
}
