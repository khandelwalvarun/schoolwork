import { Link } from "react-router-dom";
import { useState } from "react";
import { useUiPrefs } from "../components/useUiPrefs";
import { api } from "../api";

function SyncCadence() {
  const { prefs, loaded } = useUiPrefs();
  const [interval, setInterval] = useState<number>(prefs.sync_interval_hours || 1);
  const [startH, setStartH] = useState<number>(prefs.sync_window_start_hour ?? 8);
  const [endH, setEndH] = useState<number>(prefs.sync_window_end_hour ?? 22);
  const [status, setStatus] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const save = async () => {
    setStatus("saving…");
    try {
      await fetch("/api/ui-prefs", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sync_interval_hours: interval,
          sync_window_start_hour: startH,
          sync_window_end_hour: endH,
        }),
      });
      setStatus("saved");
      setTimeout(() => setStatus(null), 2000);
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  };

  const syncNow = async () => {
    setSyncing(true);
    try {
      await api.syncNow();
      setStatus("sync queued");
      setTimeout(() => setStatus(null), 3000);
    } finally {
      setSyncing(false);
    }
  };

  if (!loaded) return null;
  return (
    <section className="surface p-5 mb-4">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <div className="font-semibold">Veracross sync cadence</div>
          <div className="text-xs text-gray-500 mt-0.5">
            How often the scraper polls the portal. Runs inside the active
            window (IST). Survives server restarts — stored in
            <code className="mx-1">data/ui_prefs.json</code>.
          </div>
        </div>
        <div className="flex gap-2 items-center">
          {status && <span className="text-xs text-gray-500">{status}</span>}
          <button
            className="px-3 py-1 border border-gray-300 text-sm rounded hover:bg-gray-50"
            onClick={syncNow}
            disabled={syncing}
          >
            {syncing ? "Syncing…" : "Sync now"}
          </button>
          <button
            className="px-3 py-1 bg-blue-700 text-white text-sm rounded hover:bg-blue-800"
            onClick={save}
          >
            Save
          </button>
        </div>
      </div>
      <div className="flex items-center gap-6 text-sm flex-wrap">
        <label className="flex items-center gap-2">
          Every
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={interval}
            onChange={(e) => setInterval(Number(e.target.value))}
          >
            {[1, 2, 3, 4, 6, 8, 12, 24].map((h) => (
              <option key={h} value={h}>{h} hour{h > 1 ? "s" : ""}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Active window
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={startH}
            onChange={(e) => setStartH(Number(e.target.value))}
          >
            {Array.from({ length: 24 }, (_, i) => i).map((h) => (
              <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
            ))}
          </select>
          <span className="text-gray-400">→</span>
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={endH}
            onChange={(e) => setEndH(Number(e.target.value))}
          >
            {Array.from({ length: 24 }, (_, i) => i).map((h) => (
              <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
            ))}
          </select>
          <span className="text-xs text-gray-500">IST</span>
        </label>
      </div>
    </section>
  );
}

export default function Settings() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Settings</h2>
      <SyncCadence />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link to="/settings/veracross" className="surface p-5 hover:bg-gray-50">
          <div className="font-semibold text-lg">Veracross login</div>
          <div className="text-sm text-gray-600 mt-1">
            Portal URL, username, password. Sync health, last-success/failure,
            recent runs. Remote CAPTCHA solver when a re-auth is needed.
          </div>
        </Link>
        <Link to="/settings/channels" className="surface p-5 hover:bg-gray-50">
          <div className="font-semibold text-lg">Channels</div>
          <div className="text-sm text-gray-600 mt-1">
            Per-channel threshold, mute list, quiet hours, rate limits. Send test messages.
          </div>
        </Link>
        <Link to="/settings/syllabus" className="surface p-5 hover:bg-gray-50">
          <div className="font-semibold text-lg">Syllabus calibration</div>
          <div className="text-sm text-gray-600 mt-1">
            Override learning-cycle dates. Mark topics covered / skipped / delayed.
          </div>
        </Link>
      </div>
    </div>
  );
}
