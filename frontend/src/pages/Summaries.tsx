import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

export default function Summaries() {
  const [kind, setKind] = useState<string>("");
  const { data } = useQuery({
    queryKey: ["summaries", kind],
    queryFn: () => api.summaries(kind || undefined),
  });
  const rows = data || [];
  const [openId, setOpenId] = useState<number | null>(null);
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Past digests</h2>
        <select
          className="border border-gray-300 rounded px-2 py-1 text-sm"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">All kinds</option>
          <option value="digest_4pm">Daily (4pm)</option>
          <option value="weekly">Weekly</option>
          <option value="digest_preview">Previews</option>
          <option value="cycle_review">Cycle review</option>
        </select>
      </div>
      {rows.length === 0 && <div className="text-gray-500">No stored summaries yet.</div>}
      <div className="space-y-3">
        {rows.map((s) => {
          const open = openId === s.id;
          return (
            <div key={s.id} className="bg-white border border-gray-200 rounded shadow-sm">
              <button
                className="w-full flex items-baseline justify-between p-3 text-left hover:bg-gray-50"
                onClick={() => setOpenId(open ? null : s.id)}
              >
                <div>
                  <b>{s.period_start}</b>
                  <span className="text-xs text-gray-500 ml-2">· {s.kind}</span>
                </div>
                <div className="text-xs text-gray-500">{s.model_used}</div>
              </button>
              {open && (
                <pre className="text-xs bg-gray-50 border-t border-gray-100 p-3 whitespace-pre-wrap max-h-96 overflow-auto">{s.content_md}</pre>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
