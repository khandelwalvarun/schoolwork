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
  const TIERS: { tier: string; title: string; when: string; what: string; tone: string }[] = [
    {
      tier: "light", title: "Light",
      when: `Every ${interval}h between ${String(startH).padStart(2,"0")}:00 and ${String(endH).padStart(2,"0")}:00 IST`,
      what: "Planner + messages. New-item detail only. Devanagari repair runs async after.",
      tone: "bg-blue-50 border-blue-200",
    },
    {
      tier: "medium", title: "Medium",
      when: "Daily at 06:00 IST",
      what: "Light + grades (using cached period IDs) + attachment repair for items with stale detail (>24h).",
      tone: "bg-amber-50 border-amber-200",
    },
    {
      tier: "heavy", title: "Heavy",
      when: "Sunday 07:30 IST",
      what: "Medium + grading-period rediscovery + class-roster revalidation + full attachment re-fetch + syllabus recheck.",
      tone: "bg-purple-50 border-purple-200",
    },
  ];
  return (
    <section className="surface p-5 mb-4">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <div className="font-semibold">Veracross sync cadence</div>
          <div className="text-xs text-gray-500 mt-0.5">
            Three tiers — light for freshness, medium for grades, heavy to
            re-verify stable data once a week. Only the light tier's cadence
            is tunable.
          </div>
        </div>
        <div className="flex gap-2 items-center">
          {status && <span className="text-xs text-gray-500">{status}</span>}
          <button
            className="px-3 py-1 border border-gray-300 text-sm rounded hover:bg-gray-50"
            onClick={syncNow}
            disabled={syncing}
            title="Run a light sync immediately"
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
      <div className="flex items-center gap-6 text-sm flex-wrap mb-4">
        <label className="flex items-center gap-2">
          Light tier: every
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

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {TIERS.map((t) => (
          <div key={t.tier} className={`rounded border p-3 text-sm ${t.tone}`}>
            <div className="font-semibold mb-1">{t.title}</div>
            <div className="text-xs text-gray-700 mb-1">{t.when}</div>
            <div className="text-xs text-gray-600">{t.what}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NavLayoutToggle() {
  const { prefs, loaded } = useUiPrefs();
  const value = prefs.nav_layout ?? "horizontal";
  const set = (next: "horizontal" | "sidebar") => {
    fetch("/api/ui-prefs", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...prefs, nav_layout: next }),
    }).then(() => window.location.reload());
  };
  return (
    <section className="surface p-5 mb-4">
      <div className="font-semibold text-lg mb-1">Navigation layout</div>
      <div className="text-sm text-gray-600 mb-3">
        Choose how the app shell is structured. The left sidebar is denser
        and groups per-kid pages together; the horizontal nav is the
        original wrap-flex layout.
      </div>
      {loaded && (
        <div className="flex gap-2">
          {([
            { v: "horizontal", label: "Horizontal (top wrap)" },
            { v: "sidebar",    label: "Left sidebar (Linear-style)" },
          ] as const).map((opt) => (
            <button
              key={opt.v}
              onClick={() => set(opt.v)}
              className={
                "px-3 py-1.5 text-sm rounded border " +
                (value === opt.v
                  ? "bg-blue-700 text-white border-blue-800"
                  : "bg-white text-gray-700 border-[color:var(--line)] hover:bg-gray-50")
              }
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export default function Settings() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Settings</h2>
      <NavLayoutToggle />
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
