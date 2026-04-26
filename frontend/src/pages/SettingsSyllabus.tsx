import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api";

const CLASS_LEVELS = [4, 6];

export default function SettingsSyllabus() {
  const qc = useQueryClient();
  const [classLevel, setClassLevel] = useState<number>(CLASS_LEVELS[0]);
  const { data } = useQuery({
    queryKey: ["syllabus", classLevel],
    queryFn: () => api.syllabus(classLevel),
  });

  type Draft = Record<string, { start: string; end: string; note: string }>;
  const [draft, setDraft] = useState<Draft>({});
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    const next: Draft = {};
    for (const c of data.cycles || []) {
      next[c.name] = { start: c.start, end: c.end, note: c.override_note || "" };
    }
    setDraft(next);
  }, [data]);

  const saveCycle = async (name: string, clearIt: boolean) => {
    if (!data) return;
    setStatus(`saving ${name}…`);
    try {
      if (clearIt) {
        await api.setCycleOverride(classLevel, name, { start: null, end: null, note: null });
      } else {
        const d = draft[name];
        await api.setCycleOverride(classLevel, name, { start: d.start, end: d.end, note: d.note || null });
      }
      await qc.invalidateQueries({ queryKey: ["syllabus", classLevel] });
      setStatus(`${name} saved`);
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  };

  const setTopicStatus = async (subject: string, topic: string, status: string | null) => {
    try {
      await api.setTopicStatus(classLevel, { subject, topic, status });
      qc.invalidateQueries({ queryKey: ["syllabus", classLevel] });
    } catch (e) {
      setStatus(`error: ${String(e)}`);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-2xl font-bold">
          <Link to="/settings" className="text-gray-400 hover:text-gray-700">← </Link>
          Syllabus calibration
        </h2>
        <div className="flex items-center gap-2 text-sm">
          <span>Class</span>
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={classLevel}
            onChange={(e) => setClassLevel(Number(e.target.value))}
          >
            {CLASS_LEVELS.map((cl) => <option key={cl} value={cl}>{cl}</option>)}
          </select>
          {status && <span className="text-xs text-gray-600 ml-2">{status}</span>}
        </div>
      </div>

      {!data && (
        <div className="space-y-3" aria-hidden="true">
          <div className="skeleton h-24 w-full rounded-lg" />
          <div className="skeleton h-24 w-full rounded-lg" />
        </div>
      )}

      {data && data.cycles.map((c) => (
        <section key={c.name} className="bg-white border border-gray-200 rounded shadow-sm p-4 mb-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">{c.name} {c.overridden && <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-0.5 ml-2">Overridden</span>}</h3>
            <div className="flex gap-2">
              <button className="text-xs px-2 py-0.5 border border-gray-300 rounded hover:bg-gray-50" onClick={() => saveCycle(c.name, false)}>Save dates</button>
              {c.overridden && (
                <button className="text-xs px-2 py-0.5 border border-gray-300 rounded text-red-700 hover:bg-red-50" onClick={() => saveCycle(c.name, true)}>Clear override</button>
              )}
            </div>
          </div>
          <div className="flex gap-3 items-center text-sm mt-2">
            <label>start <input type="date" value={draft[c.name]?.start || ""} onChange={(e) => setDraft({ ...draft, [c.name]: { ...(draft[c.name] || { start: "", end: "", note: "" }), start: e.target.value } })} className="border border-gray-300 rounded px-2 py-0.5 ml-1" /></label>
            <label>end <input type="date" value={draft[c.name]?.end || ""} onChange={(e) => setDraft({ ...draft, [c.name]: { ...(draft[c.name] || { start: "", end: "", note: "" }), end: e.target.value } })} className="border border-gray-300 rounded px-2 py-0.5 ml-1" /></label>
            <input
              type="text"
              placeholder="override reason"
              className="border border-gray-300 rounded px-2 py-0.5 flex-1"
              value={draft[c.name]?.note || ""}
              onChange={(e) => setDraft({ ...draft, [c.name]: { ...(draft[c.name] || { start: "", end: "", note: "" }), note: e.target.value } })}
            />
          </div>

          <details className="mt-3">
            <summary className="text-sm text-gray-600 cursor-pointer select-none">Topics ({Object.keys(c.topics_by_subject || {}).length} subjects)</summary>
            <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
              {Object.entries(c.topics_by_subject || {}).map(([subj, topics]) => (
                <div key={subj}>
                  <div className="font-medium text-gray-800 mb-1">{subj}</div>
                  <ul className="space-y-0.5 text-sm">
                    {topics.map((t) => {
                      const st = c.topic_status?.[subj]?.[t]?.status;
                      return (
                        <li key={t} className="flex items-center gap-2">
                          <select
                            className="border border-gray-300 rounded text-xs px-1"
                            value={st || ""}
                            onChange={(e) => setTopicStatus(subj, t, e.target.value || null)}
                          >
                            <option value="">·</option>
                            <option value="in_progress">🟡 in progress</option>
                            <option value="covered">✅ covered</option>
                            <option value="delayed">⏳ delayed</option>
                            <option value="skipped">⏭️ skipped</option>
                          </select>
                          <span>{t}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </details>
        </section>
      ))}
    </div>
  );
}
