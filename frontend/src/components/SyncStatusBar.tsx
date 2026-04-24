import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { formatRelative } from "../util/dates";
import RemoteLoginModal from "./RemoteLoginModal";

/** Global sync-health banner. Lives under the top nav on every page.
 * Colors:
 *   green  — last sync ok; shows "Synced 3h ago"
 *   amber  — needs_reauth or auth_failure — clickable CTA to Re-authenticate
 *   red    — any other sync failure
 *   blue   — currently syncing
 *
 * When `needs_reauth` first appears, we auto-open the RemoteLoginModal
 * exactly once per session (so it doesn't nag on every navigation).
 */

type Health = {
  healthy: boolean;
  currently_running: boolean;
  latest_status: string;
  needs_reauth: boolean;
  consecutive_failures: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  cause_code: string;
  cause_label: string;
  cause_hint: string;
  suggested_action: string | null;
  storage_state_exists: boolean;
};

const AUTO_PROMPT_KEY = "pc:reauth-prompted";

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    headers: opts?.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export default function SyncStatusBar() {
  const { data: health, refetch } = useQuery({
    queryKey: ["vc-health-bar"],
    queryFn: () => fetchJson<Health>("/api/veracross/status"),
    refetchInterval: 30_000,
  });
  const [dismissed, setDismissed] = useState(false);
  const [showReauth, setShowReauth] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Auto-prompt once per browser session when reauth is needed
  useEffect(() => {
    if (!health?.needs_reauth) return;
    try {
      if (sessionStorage.getItem(AUTO_PROMPT_KEY) === "1") return;
      sessionStorage.setItem(AUTO_PROMPT_KEY, "1");
      setShowReauth(true);
    } catch { /* private mode */ }
  }, [health?.needs_reauth]);

  if (!health) return null;

  const tryNow = async () => {
    setSyncing(true);
    try {
      await fetch("/api/sync", { method: "POST" });
      setTimeout(() => refetch(), 1500);
    } finally {
      setSyncing(false);
    }
  };

  // Hide the bar when healthy AND a successful sync within last 4h — cuts clutter.
  const hideWhenHealthy = (() => {
    if (!health.healthy || !health.last_success_at) return false;
    try {
      const last = new Date(health.last_success_at).getTime();
      return Date.now() - last < 4 * 60 * 60 * 1000;
    } catch {
      return false;
    }
  })();
  if (hideWhenHealthy && dismissed) return null;

  let cls = "";
  let label: React.ReactNode = null;
  let cta: React.ReactNode = null;

  if (health.currently_running) {
    cls = "bg-blue-50 border-blue-200 text-blue-800";
    label = <span><span className="animate-pulse">●</span> Syncing with Veracross…</span>;
  } else if (health.needs_reauth) {
    cls = "bg-amber-50 border-amber-300 text-amber-900";
    label = (
      <span>
        <b>{health.cause_label}</b>
        {health.cause_hint && <span className="text-amber-800 font-normal ml-2">{health.cause_hint}</span>}
      </span>
    );
    cta = (
      <button
        onClick={() => setShowReauth(true)}
        className="px-3 py-1 bg-amber-600 text-white text-xs rounded hover:bg-amber-700 font-medium"
      >
        Re-authenticate
      </button>
    );
  } else if (!health.healthy) {
    cls = "bg-red-50 border-red-200 text-red-800";
    label = (
      <span>
        <b>Sync failing</b>
        <span className="ml-2 font-normal">· {health.cause_label}</span>
        {health.consecutive_failures > 1 && (
          <span className="ml-2 text-red-600 font-normal">· {health.consecutive_failures} failures in a row</span>
        )}
        {health.cause_hint && <span className="ml-2 font-normal text-red-700">· {health.cause_hint}</span>}
      </span>
    );
    cta = (
      <>
        <button onClick={tryNow} disabled={syncing}
                className="px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 font-medium disabled:opacity-50">
          {syncing ? "…" : "Retry now"}
        </button>
        <Link to="/settings/veracross" className="text-xs underline text-red-700">View details</Link>
      </>
    );
  } else {
    cls = "bg-emerald-50 border-emerald-200 text-emerald-800";
    label = (
      <span>
        <b>✓ Synced</b>
        <span className="ml-2 font-normal">
          {health.last_success_at ? formatRelative(health.last_success_at) : "recently"}
        </span>
      </span>
    );
    cta = (
      <button
        onClick={() => setDismissed(true)}
        className="text-xs text-emerald-700/70 hover:text-emerald-900"
        title="Dismiss (bar stays hidden for this session)"
      >
        ✕
      </button>
    );
  }

  return (
    <>
      <div className={`border-b text-sm ${cls}`}>
        <div className="max-w-6xl mx-auto px-5 py-1.5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">{label}</div>
          <div className="flex items-center gap-2">{cta}</div>
        </div>
      </div>
      {showReauth && (
        <RemoteLoginModal onClose={() => { setShowReauth(false); refetch(); }} />
      )}
    </>
  );
}
