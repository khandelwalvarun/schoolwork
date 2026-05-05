import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { api, Assignment, SpellBeeList, StatusHistoryEntry } from "../api";
import Attachments from "./Attachments";
import { AssignmentAskSummary } from "./AssignmentAskSummary";
import { GradeAnomalyCard } from "./GradeAnomalyCard";
import { ItemCommentsThread } from "./ItemCommentsThread";
import { SelfPredictionControl } from "./SelfPredictionControl";
import { WorthAChatToggle } from "./WorthAChatToggle";
import { EffectiveStatusChip } from "./StatusPopover";
import { formatDate, formatDateTime } from "../util/dates";

const SPELLBEE_RE = /spell(?:ing)?\s*bee/i;
const LIST_NUM_RE = /\blist\s*[-#]?\s*(\d{1,3})\b/i;

function detectListNumber(...texts: (string | null | undefined)[]): number | null {
  for (const t of texts) {
    if (!t) continue;
    const m = t.match(LIST_NUM_RE);
    if (m) {
      const n = parseInt(m[1], 10);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

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

  const isSpellBee = useMemo(
    () => SPELLBEE_RE.test(`${a.title ?? ""} ${a.title_en ?? ""} ${a.notes_en ?? ""} ${a.normalized?.body ?? ""}`),
    [a.title, a.title_en, a.notes_en, a.normalized?.body],
  );
  const spellBeeListNum = useMemo(
    () => (isSpellBee ? detectListNumber(a.title, a.title_en, a.notes_en, a.normalized?.body) : null),
    [isSpellBee, a.title, a.title_en, a.notes_en, a.normalized?.body],
  );
  const { data: spellBeeLists } = useQuery<SpellBeeList[]>({
    queryKey: ["spellbee-lists", a.child_id],
    queryFn: () => api.spellbeeLists(a.child_id),
    enabled: isSpellBee,
  });
  const matchingList = useMemo(() => {
    if (!spellBeeLists || spellBeeListNum == null) return null;
    return spellBeeLists.find((l) => l.number === spellBeeListNum) ?? null;
  }, [spellBeeLists, spellBeeListNum]);

  useEffect(() => {
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-drawer flex" style={{ background: "rgba(0,0,0,0.3)" }} onClick={onClose}>
      <div
        className="ml-auto w-[540px] h-full bg-white shadow-2xl overflow-y-auto slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Compact header: subject + title + a single inline meta
            row with chip · date · snooze · priority. The "due" word
            is dropped (the date alone is enough — for grades it's
            the graded date, for assignments it's the due date) and
            the body text uses text-meta to harmonise with the
            tray-strip vocabulary on Today. */}
        <div className="px-5 py-3 border-b border-gray-200 sticky top-0 bg-white flex items-baseline justify-between gap-3">
          <div className="min-w-0">
            <div className="text-meta text-gray-500">{a.subject}</div>
            <h3 className="text-lede font-bold leading-tight">{a.title}</h3>
            {a.title_en && a.title_en !== a.title && (
              <div className="text-body text-gray-600 italic">→ {a.title_en}</div>
            )}
            <div className="mt-1.5 flex items-center gap-2 text-meta text-gray-600 flex-wrap">
              <EffectiveStatusChip a={a} />
              {a.due_or_date && <span>· {formatDate(a.due_or_date)}</span>}
              {a.snooze_until && <span>· 💤 {a.snooze_until}</span>}
              {a.priority > 0 && <span className="text-amber-600">· {"★".repeat(a.priority)}</span>}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-xl text-gray-400 hover:text-gray-700 leading-none shrink-0"
          >
            ×
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          <GradeAnomalyCard a={a} />
          {isSpellBee && (
            <section className="bg-amber-50 border border-amber-200 rounded p-3">
              <div className="text-xs font-semibold text-amber-900 uppercase mb-1">🐝 Spelling Bee</div>
              {spellBeeListNum != null && matchingList && (
                <div className="text-sm text-amber-900">
                  Referenced <b>List {spellBeeListNum}</b> — <a
                    href={matchingList.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-700 hover:underline"
                  >open {matchingList.filename}</a>
                </div>
              )}
              {spellBeeListNum != null && !matchingList && spellBeeLists && (
                <div className="text-sm text-amber-900">
                  Referenced <b>List {spellBeeListNum}</b>, but no matching file in{" "}
                  <code className="text-xs">data/spellbee/</code>.{" "}
                  <Link to="/spellbee" className="text-blue-700 hover:underline">Browse lists →</Link>
                </div>
              )}
              {spellBeeListNum == null && (
                <div className="text-sm text-amber-900">
                  No list number mentioned in the assignment text.{" "}
                  <Link to="/spellbee" className="text-blue-700 hover:underline">Browse all lists →</Link>
                </div>
              )}
            </section>
          )}
          {a.syllabus_context && (
            <section>
              <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Syllabus</div>
              <div className="text-sm text-purple-800">↳ {a.syllabus_context}</div>
            </section>
          )}

          {/* The ask — Claude-extracted 1-line summary above the raw
              body. Auto-fired on panel open if body exists and we
              don't have a cached summary yet. */}
          {a.body && a.body.trim() && a.body.trim() !== (a.title ?? "").trim() && (
            <section>
              <AssignmentAskSummary a={a} />
              <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Description</div>
              <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                {a.body}
              </div>
              {a.notes_en && a.notes_en !== a.body && (
                <div className="text-xs text-gray-500 italic mt-1">→ {a.notes_en}</div>
              )}
            </section>
          )}

          <SelfPredictionControl a={a} />

          {/* Worth-a-chat (PTM flag) — inline toggle + editable reason.
              Lives next to comments because both are "annotate this
              item for future use" actions. */}
          <WorthAChatToggle a={a} />

          {/* Per-item parent comments — observation log keyed on this
              row. Comments here are first-class signal for the LLM
              pattern-mining job + the Analysis "Ask Claude" page. */}
          <ItemCommentsThread itemId={a.id} />

          {/* Advanced — tags / status notes / attachments. Collapsed
              by default per progressive disclosure: most opens of the
              drawer don't need to look at these. Auto-expanded only
              when there are >2 attachments (the user probably opened
              the drawer to see them). */}
          {(a.tags.length > 0 ||
            a.status_notes ||
            (a.attachments && a.attachments.length > 0)) && (
            <details
              className="group"
              open={(a.attachments?.length ?? 0) > 2}
            >
              <summary className="text-xs font-semibold text-gray-500 uppercase cursor-pointer flex items-center gap-2 select-none">
                <span className="text-gray-400 transition-transform group-open:rotate-90 inline-block w-3" aria-hidden>▶</span>
                <span>More</span>
                <span className="text-[10px] normal-case font-normal text-gray-400">
                  {[
                    a.tags.length > 0 ? `${a.tags.length} tag${a.tags.length === 1 ? "" : "s"}` : null,
                    a.status_notes ? "notes" : null,
                    (a.attachments?.length ?? 0) > 0
                      ? `${a.attachments?.length} file${a.attachments?.length === 1 ? "" : "s"}`
                      : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </summary>
              <div className="mt-2 space-y-3">
                {a.tags.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Tags</div>
                    <div className="flex flex-wrap gap-1">
                      {a.tags.map((t) => (
                        <span key={t} className="chip-blue">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
                {a.status_notes && (
                  <div>
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Notes</div>
                    <div className="text-sm whitespace-pre-wrap">{a.status_notes}</div>
                  </div>
                )}
                {a.attachments && a.attachments.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Attachments</div>
                    <Attachments items={a.attachments} />
                  </div>
                )}
              </div>
            </details>
          )}

          {/* History — hidden by default. Most parents don't need to
              see every status flip. Open if you want to audit. */}
          {history && history.length > 0 && (
            <details className="group">
              <summary className="text-xs font-semibold text-gray-500 uppercase cursor-pointer flex items-center gap-2 select-none">
                <span className="text-gray-400 transition-transform group-open:rotate-90 inline-block w-3" aria-hidden>▶</span>
                <span>Activity ({history.length})</span>
              </summary>
              <ol className="mt-2 space-y-2">
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
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
