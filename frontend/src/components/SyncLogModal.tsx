import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { formatDateTime, formatRelative } from "../util/dates";

/** Modal viewer for sync runs + their captured log text.
 *
 *  - Run list (left): reverse-chrono by default; toggle to oldest→newest.
 *  - Log text (right): emitted lines in STRICT chronological order
 *    (append-only from the scraper). Each line is classified by its level
 *    prefix (INFO / WARN / ERROR) and color-coded.
 *  - Health banner if log capture looks broken (missing sentinels).
 *  - Concurrency banner if >1 rows are at status='running'. */

type RunRow = {
  id: number;
  started_at: string | null;
  ended_at: string | null;
  trigger: string;
  status: string;
  items_new: number;
  items_updated: number;
  events_produced: number;
  notifications_fired: number;
  error: string | null;
  has_log: boolean;
  log_length: number;
};

type RunDetail = {
  id: number;
  started_at: string | null;
  ended_at: string | null;
  trigger: string;
  status: string;
  error: string | null;
  log_text: string;
  log_line_count: number;
  log_capture_healthy: boolean;
  has_start_sentinel: boolean;
  has_end_sentinel: boolean;
};

type ConcurrencyCheck = {
  count: number;
  multiple_running: boolean;
  runs: Array<{ id: number; age_sec: number; trigger: string; stale: boolean; started_at: string | null }>;
};

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    headers: opts?.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function StatusDot({ status }: { status: string }) {
  const cls =
    status === "ok"       ? "bg-emerald-500"
  : status === "running"  ? "bg-blue-500 animate-pulse"
  : status === "partial"  ? "bg-amber-500"
  : status === "failed"   ? "bg-red-500"
  : status === "skipped_concurrent" ? "bg-gray-400"
  : "bg-gray-400";
  return <span className={`inline-block w-2 h-2 rounded-full ${cls}`} aria-label={status} />;
}

function parseIso(iso: string): number {
  // Backend emits naive UTC timestamps (SQLite strips the tz-aware info on
  // DateTime(timezone=True) columns). JS's Date constructor treats naive
  // strings as LOCAL time, which was inflating elapsed-time by the IST
  // offset (5.5h) when one side was naive and the other was Date.now().
  // Mirror the fix in util/dates.ts::parseLocal here.
  const hasTz = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTz ? iso : iso + "Z").getTime();
}

function durationLabel(a: string | null, b: string | null): string {
  if (!a) return "—";
  const start = parseIso(a);
  const end = b ? parseIso(b) : Date.now();
  const sec = Math.round((end - start) / 1000);
  if (sec < 0) return "—";
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

function LogLine({ line }: { line: string }) {
  // Line format: "HH:MM:SS  LEVEL  logger.name: message"
  // Color-code by LEVEL keyword so scanning is fast.
  const isWarn  = /\s+WARN(ING)?\s+/.test(line) || /WARNING/.test(line);
  const isError = /\s+ERROR\s+/.test(line) || /ERROR/.test(line) && /: /.test(line);
  const isSentinel = line.includes("=== sync started") || line.includes("=== sync ended");
  const isDebug = /\s+DEBUG\s+/.test(line);
  let cls = "text-gray-800";
  if (isSentinel) cls = "text-purple-700 font-semibold bg-purple-50";
  else if (isError) cls = "text-red-700 bg-red-50";
  else if (isWarn) cls = "text-amber-800 bg-amber-50";
  else if (isDebug) cls = "text-gray-500";
  return (
    <div className={`px-2 py-[1px] ${cls}`}>
      {line || "\u00a0"}
    </div>
  );
}

export default function SyncLogModal({ onClose }: { onClose: () => void }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [pruneStatus, setPruneStatus] = useState<string | null>(null);
  const [oldestFirst, setOldestFirst] = useState(false);

  const { data: runsRaw, refetch: refetchRuns } = useQuery({
    queryKey: ["sync-runs-log-modal"],
    queryFn: () => fetchJson<RunRow[]>("/api/sync-runs?limit=60"),
    refetchInterval: 5_000,
  });
  const runs = runsRaw || [];

  const { data: concurrency } = useQuery({
    queryKey: ["sync-concurrency-check"],
    queryFn: () => fetchJson<ConcurrencyCheck>("/api/sync-runs/concurrency-check"),
    refetchInterval: 10_000,
  });

  const sortedRuns = oldestFirst ? [...runs].reverse() : runs;
  const selected = selectedId
    ? runs.find((r) => r.id === selectedId)
    : sortedRuns[0];

  const { data: detail, refetch: refetchDetail } = useQuery({
    queryKey: ["sync-run-log", selected?.id],
    queryFn: () => fetchJson<RunDetail>(`/api/sync-runs/${selected!.id}/log`),
    enabled: !!selected?.id,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });

  useEffect(() => {
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  const prune = async () => {
    setPruneStatus("pruning…");
    try {
      const r = await fetchJson<{ deleted: number; cutoff: string }>(
        "/api/sync-runs/prune?days=7", { method: "POST" },
      );
      setPruneStatus(`deleted ${r.deleted} rows older than ${r.cutoff.slice(0, 10)}`);
      refetchRuns();
    } catch (e) {
      setPruneStatus(`error: ${String(e)}`);
    }
    setTimeout(() => setPruneStatus(null), 4000);
  };

  const logLines = (detail?.log_text || "").split("\n");

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center fade-in"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-2xl border border-[color:var(--line)] flex flex-col"
        style={{ width: "min(96vw, 1100px)", height: "min(90vh, 800px)" }}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--line)]">
          <div>
            <h3 className="text-lg font-semibold">Sync log</h3>
            <div className="text-xs text-gray-500 mt-0.5">
              Logs retained for <b>7 days</b> · auto-pruned daily at 03:10.
              Only one sync runs at a time (in-process lock + startup orphan cleanup).
            </div>
          </div>
          <button onClick={onClose} className="text-2xl text-gray-400 hover:text-gray-700 leading-none">×</button>
        </div>

        {concurrency?.multiple_running && (
          <div className="bg-amber-50 border-b border-amber-300 px-5 py-2 text-xs text-amber-900">
            <b>⚠ {concurrency.count} syncs show as running.</b>
            {" "}That shouldn't happen — orphaned rows normally close on server restart.
            {" "}<button className="underline" onClick={async () => {
              await fetchJson("/api/sync-runs/concurrency-check");
              refetchRuns();
            }}>Re-check</button>
          </div>
        )}

        <div className="flex flex-1 overflow-hidden">
          {/* Left: run list */}
          <aside className="w-[330px] border-r border-[color:var(--line)] overflow-y-auto flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b border-[color:var(--line-soft)] bg-gray-50 text-xs">
              <span className="text-gray-600">{runs.length} runs</span>
              <button
                onClick={() => setOldestFirst((v) => !v)}
                className="text-blue-700 hover:underline"
                title="Toggle chrono order"
              >
                {oldestFirst ? "Oldest first ↑" : "Newest first ↓"}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {sortedRuns.map((r) => {
                const isSelected = selected?.id === r.id;
                return (
                  <button
                    key={r.id}
                    onClick={() => setSelectedId(r.id)}
                    className={
                      "w-full text-left px-3 py-2 border-b border-[color:var(--line-soft)] " +
                      (isSelected ? "bg-[color:var(--accent-bg)]" : "hover:bg-gray-50")
                    }
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <StatusDot status={r.status} />
                      <span className="font-medium">#{r.id}</span>
                      <span className="text-gray-600">{r.status}</span>
                      <span className="text-xs text-gray-500 ml-auto">{r.trigger}</span>
                    </div>
                    <div className="text-xs text-gray-600 mt-0.5" title={r.started_at ?? ""}>
                      {formatDateTime(r.started_at)} · {durationLabel(r.started_at, r.ended_at)}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      +{r.items_new} new · ~{r.items_updated} upd · {r.events_produced} ev
                      {r.notifications_fired > 0 && <> · 🔔 {r.notifications_fired}</>}
                      {r.has_log
                        ? <> · <span className="text-gray-400">log ({Math.round(r.log_length / 1024)}KB)</span></>
                        : <> · <span className="text-amber-700">no log</span></>}
                    </div>
                    {r.error && (
                      <div className="text-xs text-red-700 mt-0.5 truncate" title={r.error}>{r.error}</div>
                    )}
                  </button>
                );
              })}
              {runs.length === 0 && (
                <div className="p-4 text-sm text-gray-500">No sync runs yet.</div>
              )}
            </div>
          </aside>

          {/* Right: log text */}
          <main className="flex-1 overflow-hidden flex flex-col">
            {selected && detail ? (
              <>
                <div className="px-4 py-3 border-b border-[color:var(--line-soft)] text-sm bg-gray-50">
                  <div className="flex items-center gap-3 flex-wrap">
                    <StatusDot status={selected.status} />
                    <div className="font-medium">Run #{selected.id} · {selected.status}</div>
                    <span className="text-xs text-gray-500">
                      {formatRelative(selected.started_at)} · {durationLabel(selected.started_at, selected.ended_at)}
                    </span>
                    <span className="text-xs text-gray-500">
                      {detail.log_line_count} log line{detail.log_line_count === 1 ? "" : "s"}
                    </span>
                    <button
                      onClick={() => refetchDetail()}
                      className="ml-auto text-xs text-blue-700 hover:underline"
                    >
                      Refresh
                    </button>
                  </div>
                  {selected.error && (
                    <div className="mt-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2 whitespace-pre-wrap">
                      {selected.error}
                    </div>
                  )}
                  {!detail.log_capture_healthy && (
                    <div className="mt-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
                      ⚠ Log capture looks incomplete —
                      {!detail.has_start_sentinel && " missing start sentinel"}
                      {!detail.has_start_sentinel && !detail.has_end_sentinel && " and"}
                      {!detail.has_end_sentinel && selected.status !== "running" && " missing end sentinel"}.
                      Handler may have detached early or the logger wasn't registered.
                    </div>
                  )}
                </div>
                <div
                  className="flex-1 overflow-auto text-xs font-mono leading-snug bg-white text-gray-800"
                  aria-label={`Log for run ${selected.id}`}
                >
                  {logLines.length === 1 && !logLines[0] ? (
                    <div className="p-6 text-gray-400 italic text-center">
                      {selected.status === "running"
                        ? "(streaming — polling every 2s while this run is in progress)"
                        : "(no log captured for this run)"}
                    </div>
                  ) : (
                    logLines.map((line, i) => <LogLine key={i} line={line} />)
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
                Select a run to view its log.
              </div>
            )}
          </main>
        </div>

        <div className="px-4 py-2 border-t border-[color:var(--line-soft)] text-xs text-gray-500 flex items-center justify-between">
          <span>
            {runs.length} runs in window · retention 7 days.
            {pruneStatus && <span className="ml-3 text-gray-700">{pruneStatus}</span>}
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={prune}
              className="text-xs text-gray-600 hover:text-gray-900"
              title="Delete sync runs older than 7 days now"
            >
              Prune now
            </button>
            <span><span className="kbd">Esc</span> to close</span>
          </div>
        </div>
      </div>
    </div>
  );
}
