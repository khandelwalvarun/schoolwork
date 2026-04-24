import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import RemoteLoginModal from "../components/RemoteLoginModal";
import { formatDateTime, formatRelative } from "../util/dates";

type CredView = {
  portal_url: string;
  username: string;
  has_password: boolean;
  password_length: number;
  override_active: boolean;
  override_fields: string[];
};

type HealthView = {
  healthy: boolean;
  needs_reauth: boolean;
  consecutive_failures: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  storage_state_exists: boolean;
  recent_runs: Array<{
    id: number;
    status: string;
    started_at: string | null;
    ended_at: string | null;
    duration_sec: number | null;
    items_new: number;
    items_updated: number;
    events_produced: number;
    error: string;
  }>;
};

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function HealthCard({ health }: { health: HealthView }) {
  const badge =
    health.needs_reauth
      ? { cls: "bg-amber-100 text-amber-900 border-amber-300", label: "Re-auth required" }
    : !health.healthy
      ? { cls: "bg-red-100 text-red-800 border-red-300", label: "Sync failing" }
    : { cls: "bg-emerald-100 text-emerald-800 border-emerald-300", label: "Healthy" };
  return (
    <section className="surface p-5 mb-4">
      <div className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <div className="font-semibold">Sync health</div>
          <div className="text-xs text-gray-500 mt-0.5">
            Session cookies on disk: <b>{health.storage_state_exists ? "yes" : "no"}</b> ·
            consecutive failures: <b>{health.consecutive_failures}</b>
          </div>
        </div>
        <span className={`text-xs font-medium px-2.5 py-1 rounded border ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-sm">
        <div>
          <div className="h-section text-emerald-700">Last success</div>
          <div>{health.last_success_at
            ? <span title={health.last_success_at}>{formatRelative(health.last_success_at)}</span>
            : <span className="text-gray-400">never</span>}</div>
        </div>
        <div>
          <div className="h-section text-red-700">Last failure</div>
          <div>{health.last_failure_at
            ? <span title={health.last_failure_at}>{formatRelative(health.last_failure_at)}</span>
            : <span className="text-gray-400">none</span>}</div>
          {health.last_error && (
            <div className="mt-1 text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2 whitespace-pre-wrap">
              {health.last_error}
            </div>
          )}
        </div>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-sm text-gray-600">Recent sync runs</summary>
        <table className="w-full text-xs mt-2">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="py-1 pr-3">When</th>
              <th className="py-1 pr-3">Status</th>
              <th className="py-1 pr-3">New</th>
              <th className="py-1 pr-3">Upd</th>
              <th className="py-1 pr-3">Events</th>
              <th className="py-1 pr-3">Error</th>
            </tr>
          </thead>
          <tbody>
            {health.recent_runs.map((r) => (
              <tr key={r.id} className="border-t border-[color:var(--line-soft)]">
                <td className="py-1 pr-3">{formatDateTime(r.ended_at || r.started_at)}</td>
                <td className={"py-1 pr-3 " + (r.status === "ok" ? "text-emerald-700" : "text-red-700")}>{r.status}</td>
                <td className="py-1 pr-3">{r.items_new}</td>
                <td className="py-1 pr-3">{r.items_updated}</td>
                <td className="py-1 pr-3">{r.events_produced}</td>
                <td className="py-1 pr-3 text-gray-500 truncate max-w-[300px]">{r.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

export default function SettingsVeracross() {
  const { data: creds, refetch: refetchCreds } = useQuery({
    queryKey: ["vc-creds"],
    queryFn: () => api<CredView>("/api/veracross/credentials"),
  });
  const { data: health, refetch: refetchHealth } = useQuery({
    queryKey: ["vc-health"],
    queryFn: () => api<HealthView>("/api/veracross/status"),
    refetchInterval: 10_000,
  });

  const [portalUrl, setPortalUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (creds) {
      setPortalUrl(creds.portal_url || "");
      setUsername(creds.username || "");
    }
  }, [creds]);

  const save = async () => {
    setStatus("saving…");
    try {
      await api("/api/veracross/credentials", {
        method: "PUT",
        body: JSON.stringify({
          portal_url: portalUrl,
          username,
          ...(password ? { password } : {}),
        }),
      });
      setPassword("");
      setStatus("saved");
      refetchCreds();
      setTimeout(() => setStatus(null), 2500);
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  };

  const clearOverride = async () => {
    setStatus("clearing override…");
    try {
      await api("/api/veracross/credentials", {
        method: "PUT",
        body: JSON.stringify({ portal_url: "", username: "", password: "" }),
      });
      setStatus("cleared — using .env values");
      refetchCreds();
      setTimeout(() => setStatus(null), 2500);
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">
        <Link to="/settings" className="text-gray-400 hover:text-gray-700 text-sm mr-2">← Settings</Link>
        Veracross
      </h2>

      {health && <HealthCard health={health} />}

      {health?.needs_reauth && (
        <div className="mb-4 p-4 rounded border border-amber-300 bg-amber-50 text-amber-900 text-sm flex items-center justify-between gap-3 flex-wrap">
          <div>
            <b>Veracross session expired.</b> Re-authenticate — the CAPTCHA
            needs a human to solve it. Open the remote login window below.
          </div>
          <button
            className="px-3 py-1.5 bg-amber-600 text-white rounded hover:bg-amber-700"
            onClick={() => setModalOpen(true)}
          >
            Re-authenticate
          </button>
        </div>
      )}

      <section className="surface p-5 mb-4">
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <div className="font-semibold">Credentials</div>
            <div className="text-xs text-gray-500 mt-0.5">
              Stored encrypted at-rest? <b>No</b> — plain JSON at
              <code className="mx-1">data/veracross_creds.json</code> (chmod 0600, gitignored).
              Fallback to
              <code className="mx-1">.env</code>.
              {creds?.override_active && (
                <span className="ml-2 text-amber-700">Override active: {creds.override_fields.join(", ")}</span>
              )}
            </div>
          </div>
          <div className="flex gap-2 items-center">
            {status && <span className="text-xs text-gray-500">{status}</span>}
            {creds?.override_active && (
              <button onClick={clearOverride}
                      className="text-xs px-3 py-1 border border-red-300 text-red-700 rounded hover:bg-red-50">
                Clear override
              </button>
            )}
            <button onClick={save}
                    className="px-3 py-1.5 bg-blue-700 text-white text-sm rounded hover:bg-blue-800">
              Save
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-gray-600">Portal URL</span>
            <input className="border border-gray-300 rounded px-2 py-1" value={portalUrl}
                   onChange={(e) => setPortalUrl(e.target.value)}
                   placeholder="https://portals.veracross.eu/vasantvalleyschool/parent" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-gray-600">Username</span>
            <input className="border border-gray-300 rounded px-2 py-1" value={username}
                   onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label className="flex flex-col gap-1 md:col-span-2">
            <span className="text-xs text-gray-600">
              Password
              {creds?.has_password && !password && (
                <span className="ml-2 text-gray-400">· currently set ({creds.password_length} chars)</span>
              )}
            </span>
            <input
              className="border border-gray-300 rounded px-2 py-1 font-mono"
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="(leave blank to keep current)"
            />
          </label>
        </div>
      </section>

      <section className="surface p-5">
        <div className="flex items-baseline justify-between mb-2">
          <div>
            <div className="font-semibold">Re-authenticate</div>
            <div className="text-xs text-gray-500 mt-0.5">
              Veracross requires reCAPTCHA on login — a human must solve it.
              The browser runs on the server (headless), streams screenshots
              here, and forwards your clicks/keys so you can sign in from any
              device on the LAN.
            </div>
          </div>
          <button onClick={() => { refetchHealth(); setModalOpen(true); }}
                  className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50">
            Open login window
          </button>
        </div>
      </section>

      {modalOpen && <RemoteLoginModal onClose={() => { setModalOpen(false); refetchHealth(); refetchCreds(); }} />}
    </div>
  );
}
