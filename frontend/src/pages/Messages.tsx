import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Assignment, MessageRow } from "../api";
import Attachments from "../components/Attachments";
import TitleBlock from "../components/TitleBlock";
import AuditDrawer from "../components/AuditDrawer";

export default function Messages() {
  const [sinceDays, setSinceDays] = useState(30);
  const [audit, setAudit] = useState<MessageRow | null>(null);
  const { data } = useQuery({
    queryKey: ["messages", sinceDays],
    queryFn: () => api.messages(sinceDays),
  });
  const rows = data || [];
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">School messages</h2>
        <select
          className="border border-gray-300 rounded px-2 py-1 text-sm"
          value={sinceDays}
          onChange={(e) => setSinceDays(Number(e.target.value))}
        >
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>
      {rows.length === 0 && <div className="text-gray-500">No messages in this window.</div>}
      <div className="space-y-3">
        {rows.map((m) => (
          <div
            key={m.id}
            className="bg-white border border-gray-200 rounded shadow-sm p-4 cursor-pointer hover:bg-gray-50"
            onClick={() => setAudit(m)}
          >
            <div className="flex items-baseline justify-between">
              <div className="flex-1 mr-2">
                <TitleBlock
                  title={m.title || m.subject || "(untitled)"}
                  titleEn={(m as unknown as { title_en?: string | null }).title_en}
                  className="font-bold"
                />
              </div>
              <div className="text-xs text-gray-500 whitespace-nowrap">{m.due_or_date || m.first_seen_at}</div>
            </div>
            {m.normalized?.teacher && (
              <div className="text-xs text-gray-500 mt-0.5">from {m.normalized.teacher}</div>
            )}
            {m.normalized?.body && (
              <div className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">{m.normalized.body}</div>
            )}
            <Attachments items={m.attachments} />
          </div>
        ))}
      </div>
      {audit && <AuditDrawer a={audit as unknown as Assignment} onClose={() => setAudit(null)} />}
    </div>
  );
}
