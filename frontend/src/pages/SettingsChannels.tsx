import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

type ChannelCfg = {
  enabled?: boolean;
  threshold?: number;
  mute_kinds?: string[];
  rate_limit?: { max_per_hour?: number; max_per_day?: number; quiet_hours_ist?: string };
};

type Config = {
  channels?: Record<string, ChannelCfg & { delivery?: string[] }>;
};

export default function SettingsChannels() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["channel-config"], queryFn: api.channelConfig });
  const [draft, setDraft] = useState<Config | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (data && !draft) setDraft(data as unknown as Config);
  }, [data, draft]);

  if (!draft) return <div>Loading…</div>;

  const updateChannel = (name: string, patch: Partial<ChannelCfg>) => {
    const cur = draft.channels?.[name] || {};
    setDraft({ ...draft, channels: { ...(draft.channels || {}), [name]: { ...cur, ...patch } } });
  };

  const save = async () => {
    setStatus("saving…");
    try {
      await api.putChannelConfig(draft);
      setStatus("saved");
      qc.invalidateQueries({ queryKey: ["channel-config"] });
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  };

  const sendTest = async (channel: string) => {
    setStatus(`sending test to ${channel}…`);
    try {
      const r = await fetch(`/api/channels/${channel}/test`, { method: "POST" });
      const j = await r.json();
      setStatus(`test → ${j.status}${j.error ? ` (${j.error})` : ""}`);
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  };

  const channels = Object.entries(draft.channels || {}).filter(([n]) => n !== "digest");
  const digestCfg = draft.channels?.digest;

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-2xl font-bold">
          <Link to="/settings" className="text-gray-400 hover:text-gray-700">← </Link>
          Channels
        </h2>
        <div className="flex gap-2 items-center">
          {status && <span className="text-xs text-gray-600">{status}</span>}
          <button className="bg-blue-700 text-white text-sm rounded px-3 py-1 hover:bg-blue-800" onClick={save}>Save</button>
        </div>
      </div>

      {channels.map(([name, cfg]) => (
        <section key={name} className="bg-white border border-gray-200 rounded shadow-sm p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold capitalize">{name}</h3>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={cfg.enabled ?? true}
                  onChange={(e) => updateChannel(name, { enabled: e.target.checked })}
                />
                enabled
              </label>
              <button
                className="text-xs px-2 py-0.5 border border-gray-300 rounded hover:bg-gray-50"
                onClick={() => sendTest(name)}
              >Send test</button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <label className="flex items-center gap-2">
              threshold
              <input
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={cfg.threshold ?? 0}
                onChange={(e) => updateChannel(name, { threshold: Number(e.target.value) })}
                className="border border-gray-300 rounded px-2 py-0.5 w-24"
              />
            </label>
            <label className="flex items-center gap-2">
              mute kinds
              <input
                type="text"
                value={(cfg.mute_kinds || []).join(", ")}
                onChange={(e) => updateChannel(name, { mute_kinds: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                className="border border-gray-300 rounded px-2 py-0.5 flex-1"
              />
            </label>
            <label className="flex items-center gap-2">
              max/hour
              <input
                type="number"
                value={cfg.rate_limit?.max_per_hour ?? ""}
                onChange={(e) => updateChannel(name, { rate_limit: { ...(cfg.rate_limit || {}), max_per_hour: e.target.value ? Number(e.target.value) : undefined } })}
                className="border border-gray-300 rounded px-2 py-0.5 w-24"
              />
            </label>
            <label className="flex items-center gap-2">
              max/day
              <input
                type="number"
                value={cfg.rate_limit?.max_per_day ?? ""}
                onChange={(e) => updateChannel(name, { rate_limit: { ...(cfg.rate_limit || {}), max_per_day: e.target.value ? Number(e.target.value) : undefined } })}
                className="border border-gray-300 rounded px-2 py-0.5 w-24"
              />
            </label>
            {name === "telegram" && (
              <label className="flex items-center gap-2 md:col-span-2">
                quiet hours (IST, e.g. 22:00-07:00)
                <input
                  type="text"
                  value={cfg.rate_limit?.quiet_hours_ist || ""}
                  onChange={(e) => updateChannel(name, { rate_limit: { ...(cfg.rate_limit || {}), quiet_hours_ist: e.target.value || undefined } })}
                  className="border border-gray-300 rounded px-2 py-0.5 flex-1"
                />
              </label>
            )}
          </div>
        </section>
      ))}

      {digestCfg && (
        <section className="bg-white border border-gray-200 rounded shadow-sm p-4 mb-4">
          <h3 className="font-semibold mb-2">Digest delivery</h3>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={digestCfg.enabled ?? true}
              onChange={(e) => updateChannel("digest", { enabled: e.target.checked } as ChannelCfg)}
            />
            enabled
          </label>
          <div className="text-sm mt-2">
            delivery channels:
            {["telegram", "email", "inapp"].map((c) => (
              <label key={c} className="ml-3 inline-flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={(digestCfg.delivery || []).includes(c)}
                  onChange={(e) => {
                    const cur = digestCfg.delivery || [];
                    const next = e.target.checked ? [...cur, c] : cur.filter((x: string) => x !== c);
                    setDraft({ ...draft, channels: { ...(draft.channels || {}), digest: { ...digestCfg, delivery: next } } });
                  }}
                />
                {c}
              </label>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
