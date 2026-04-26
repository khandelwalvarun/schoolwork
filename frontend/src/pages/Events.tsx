/**
 * Events — kid-relevant calendar surface.
 *
 * Two ways events land in the table:
 *   1. Manual entry via the form on this page.
 *   2. LLM extraction from school messages — click "Scan messages"
 *      and Claude walks recent school_message rows pulling out any
 *      dated event (audition, camp, exam, deadline, etc.).
 *
 * Layout:
 *   - Top: "Add event" form (collapsible)
 *   - Filter strip (kid · type)
 *   - Two sections: "Upcoming" (today + future, sorted ascending) and
 *     "Past" (collapsible, sorted descending).
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Child, KidEvent } from "../api";

const TYPE_TONE: Record<string, string> = {
  audition:       "border-pink-300 text-pink-800 bg-pink-50",
  competition:    "border-purple-300 text-purple-800 bg-purple-50",
  camp:           "border-amber-300 text-amber-800 bg-amber-50",
  exam:           "border-red-300 text-red-800 bg-red-50",
  test:           "border-red-200 text-red-700 bg-red-50",
  parent_meeting: "border-blue-300 text-blue-800 bg-blue-50",
  trip:           "border-emerald-300 text-emerald-800 bg-emerald-50",
  performance:    "border-fuchsia-300 text-fuchsia-800 bg-fuchsia-50",
  deadline:       "border-orange-300 text-orange-800 bg-orange-50",
  holiday:        "border-cyan-300 text-cyan-800 bg-cyan-50",
  other:          "border-gray-300 text-gray-700 bg-gray-50",
};

const TYPE_OPTIONS = [
  "audition", "competition", "camp", "exam", "test",
  "parent_meeting", "trip", "performance", "deadline",
  "holiday", "other",
];

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

function fmtRange(start: string, end: string | null): string {
  if (!end || end === start) return fmtDate(start);
  return `${fmtDate(start)} → ${fmtDate(end)}`;
}

function daysFromToday(iso: string): number {
  const today = new Date().toISOString().slice(0, 10);
  const d = new Date(iso + "T00:00:00").getTime();
  const t = new Date(today + "T00:00:00").getTime();
  return Math.round((d - t) / (24 * 60 * 60 * 1000));
}

function defaultEvent(): Partial<KidEvent> {
  const today = new Date().toISOString().slice(0, 10);
  return {
    title: "",
    start_date: today,
    event_type: "other",
    importance: 1,
    child_id: null,
  };
}

function EventForm({
  initial,
  kids,
  onSave,
  onCancel,
}: {
  initial: Partial<KidEvent>;
  kids: Child[];
  onSave: (e: Partial<KidEvent>) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Partial<KidEvent>>(initial);
  const set = (patch: Partial<KidEvent>) => setDraft({ ...draft, ...patch });

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
      <label className="flex flex-col gap-1 md:col-span-2">
        <span className="text-xs uppercase tracking-wider text-gray-500">Title</span>
        <input
          type="text"
          value={draft.title || ""}
          onChange={(e) => set({ title: e.target.value })}
          className="border border-gray-300 rounded px-2 py-1"
          placeholder="e.g. Class 6 piano audition"
          required
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-gray-500">Type</span>
        <select
          value={draft.event_type || "other"}
          onChange={(e) => set({ event_type: e.target.value })}
          className="border border-gray-300 rounded px-2 py-1"
        >
          {TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>{t.replace("_", " ")}</option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-gray-500">For kid</span>
        <select
          value={draft.child_id == null ? "" : String(draft.child_id)}
          onChange={(e) =>
            set({ child_id: e.target.value === "" ? null : Number(e.target.value) })
          }
          className="border border-gray-300 rounded px-2 py-1"
        >
          <option value="">Both / general</option>
          {kids.map((k) => (
            <option key={k.id} value={k.id}>{k.display_name}</option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-gray-500">Start date</span>
        <input
          type="date"
          value={draft.start_date || ""}
          onChange={(e) => set({ start_date: e.target.value })}
          className="border border-gray-300 rounded px-2 py-1"
          required
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-gray-500">
          End date (optional)
        </span>
        <input
          type="date"
          value={draft.end_date || ""}
          onChange={(e) => set({ end_date: e.target.value || null })}
          className="border border-gray-300 rounded px-2 py-1"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-gray-500">Time</span>
        <input
          type="time"
          value={draft.start_time || ""}
          onChange={(e) => set({ start_time: e.target.value || null })}
          className="border border-gray-300 rounded px-2 py-1"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-gray-500">Importance</span>
        <select
          value={String(draft.importance ?? 1)}
          onChange={(e) => set({ importance: Number(e.target.value) })}
          className="border border-gray-300 rounded px-2 py-1"
        >
          <option value="1">1 — normal</option>
          <option value="2">2 — important</option>
          <option value="3">3 — critical</option>
        </select>
      </label>

      <label className="flex flex-col gap-1 md:col-span-2">
        <span className="text-xs uppercase tracking-wider text-gray-500">Location</span>
        <input
          type="text"
          value={draft.location || ""}
          onChange={(e) => set({ location: e.target.value || null })}
          className="border border-gray-300 rounded px-2 py-1"
          placeholder="e.g. School auditorium"
        />
      </label>

      <label className="flex flex-col gap-1 md:col-span-2">
        <span className="text-xs uppercase tracking-wider text-gray-500">Notes</span>
        <textarea
          value={draft.description || ""}
          onChange={(e) => set({ description: e.target.value || null })}
          className="border border-gray-300 rounded px-2 py-1 h-16"
          placeholder="What's the gist?"
        />
      </label>

      <div className="md:col-span-2 flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={() => onSave(draft)}
          disabled={!draft.title || !draft.start_date}
          className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {draft.id ? "Update" : "Add"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-sm text-gray-600 hover:underline"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function Events() {
  const qc = useQueryClient();
  const [filterChild, setFilterChild] = useState<"all" | number>("all");
  const [filterType, setFilterType] = useState<string>("all");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Partial<KidEvent> | null>(null);
  const [showPast, setShowPast] = useState(false);

  const { data: kids } = useQuery({
    queryKey: ["children"],
    queryFn: () => api.children(),
    staleTime: 5 * 60_000,
  });

  const { data, isLoading } = useQuery<KidEvent[]>({
    queryKey: ["events", filterChild],
    queryFn: () =>
      api.events(filterChild === "all" ? undefined : filterChild),
    staleTime: 30_000,
  });

  const save = useMutation({
    mutationFn: (e: Partial<KidEvent>) => api.upsertEvent(e),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
      setShowForm(false);
      setEditing(null);
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteEvent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["events"] }),
  });

  const extract = useMutation({
    mutationFn: () => api.extractEventsFromMessages(60, true),
    onSuccess: (out) => {
      qc.invalidateQueries({ queryKey: ["events"] });
      console.log("event extraction:", out);
    },
  });

  const rows = (data ?? []).filter(
    (e) => filterType === "all" || e.event_type === filterType,
  );

  const today = new Date().toISOString().slice(0, 10);
  const upcoming = rows.filter((e) => e.start_date >= today);
  const past = rows.filter((e) => e.start_date < today).reverse();

  return (
    <div className="pb-12">
      <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
        <h2 className="text-2xl font-bold">Events</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => extract.mutate()}
            disabled={extract.isPending}
            className="text-xs px-2 py-1 border border-purple-300 text-purple-800 bg-purple-50 hover:bg-purple-100 rounded disabled:opacity-50"
            title="Ask Claude to read recent school messages and extract any dated events"
          >
            {extract.isPending ? "Scanning…" : "📨 Scan messages"}
          </button>
          <button
            type="button"
            onClick={() => {
              setEditing(defaultEvent());
              setShowForm(true);
            }}
            className="text-xs px-2 py-1 border border-blue-300 text-blue-800 bg-blue-50 hover:bg-blue-100 rounded"
          >
            + Add event
          </button>
        </div>
      </div>
      <p className="text-sm text-gray-600 mb-4">
        Kid-relevant moments — auditions, competitions, camps, exams, deadlines.
        Auto-extracted from school messages or typed in by you.
      </p>

      {showForm && editing && (kids?.length ?? 0) > 0 && (
        <section className="surface mb-6 p-5">
          <h3 className="font-semibold mb-3">
            {editing.id ? "Edit event" : "New event"}
          </h3>
          <EventForm
            initial={editing}
            kids={kids as Child[]}
            onSave={(e) => save.mutate(e)}
            onCancel={() => {
              setShowForm(false);
              setEditing(null);
            }}
          />
        </section>
      )}

      <div className="flex items-center gap-2 mb-4 text-xs flex-wrap">
        <span className="text-gray-500">Filter:</span>
        <select
          className="border border-gray-300 rounded px-2 py-1"
          value={filterChild === "all" ? "all" : String(filterChild)}
          onChange={(e) =>
            setFilterChild(e.target.value === "all" ? "all" : Number(e.target.value))
          }
        >
          <option value="all">All kids</option>
          {(kids as Child[] | undefined)?.map((k) => (
            <option key={k.id} value={k.id}>{k.display_name}</option>
          ))}
        </select>
        <select
          className="border border-gray-300 rounded px-2 py-1"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="all">All types</option>
          {TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>{t.replace("_", " ")}</option>
          ))}
        </select>
        <span className="ml-auto text-gray-400">
          {upcoming.length} upcoming · {past.length} past
        </span>
      </div>

      <h3 className="text-sm font-semibold text-gray-700 mb-2">Upcoming</h3>
      {isLoading ? (
        <div className="text-gray-400 mb-6">Loading…</div>
      ) : upcoming.length === 0 ? (
        <div className="surface mb-6 p-6 text-center text-sm text-gray-500">
          Nothing on the horizon. Add one above, or scan recent school messages.
        </div>
      ) : (
        <ul className="space-y-2 mb-6">
          {upcoming.map((e) => (
            <EventRow
              key={e.id}
              event={e}
              kids={(kids as Child[] | undefined) ?? []}
              onEdit={() => {
                setEditing(e);
                setShowForm(true);
              }}
              onDelete={() => remove.mutate(e.id)}
            />
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => setShowPast((v) => !v)}
        className="text-xs text-gray-500 hover:text-gray-800 mb-2"
      >
        {showPast ? "▾" : "▸"} Past events ({past.length})
      </button>
      {showPast && past.length > 0 && (
        <ul className="space-y-2 opacity-70">
          {past.map((e) => (
            <EventRow
              key={e.id}
              event={e}
              kids={(kids as Child[] | undefined) ?? []}
              onEdit={() => {
                setEditing(e);
                setShowForm(true);
              }}
              onDelete={() => remove.mutate(e.id)}
              past
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function EventRow({
  event,
  kids,
  onEdit,
  onDelete,
  past,
}: {
  event: KidEvent;
  kids: Child[];
  onEdit: () => void;
  onDelete: () => void;
  past?: boolean;
}) {
  const tone = TYPE_TONE[event.event_type || "other"] || TYPE_TONE.other;
  const days = daysFromToday(event.start_date);
  const kid = kids.find((k) => k.id === event.child_id);
  const importanceMark =
    event.importance >= 3 ? "★★★" : event.importance >= 2 ? "★★" : "";

  return (
    <li className="surface p-3 group">
      <div className="flex items-start gap-3">
        <div
          className="text-center flex-shrink-0 w-12"
          aria-label={fmtDate(event.start_date)}
        >
          <div className="text-[10px] uppercase tracking-wider text-gray-400">
            {new Date(event.start_date + "T00:00:00").toLocaleDateString("en-US", { month: "short" })}
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {new Date(event.start_date + "T00:00:00").getDate()}
          </div>
          {event.start_time && (
            <div className="text-[9px] text-gray-500">{event.start_time}</div>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-900">{event.title}</span>
            {event.event_type && (
              <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${tone}`}>
                {event.event_type.replace("_", " ")}
              </span>
            )}
            {kid && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border border-purple-200 bg-purple-50 text-purple-800">
                {kid.display_name}
              </span>
            )}
            {!kid && event.child_id == null && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border border-gray-200 bg-gray-50 text-gray-600">
                both kids
              </span>
            )}
            {importanceMark && (
              <span className="text-amber-600 text-xs">{importanceMark}</span>
            )}
            {!past && (
              <span className="ml-auto text-xs text-gray-500">
                {days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`}
              </span>
            )}
          </div>
          {event.description && (
            <div className="text-sm text-gray-700 mt-1 leading-snug">
              {event.description}
            </div>
          )}
          <div className="text-[11px] text-gray-500 mt-1 flex items-center gap-2 flex-wrap">
            <span>{fmtRange(event.start_date, event.end_date)}</span>
            {event.location && <><span>·</span><span>{event.location}</span></>}
            {event.source !== "manual" && (
              <>
                <span>·</span>
                <span className="italic">via {event.source}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <button
            type="button"
            onClick={onEdit}
            className="text-[11px] text-blue-700 hover:underline"
          >
            edit
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="text-[11px] text-red-700 hover:underline"
          >
            delete
          </button>
        </div>
      </div>
    </li>
  );
}
