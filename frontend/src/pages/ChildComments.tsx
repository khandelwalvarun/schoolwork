import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Assignment, Comment } from "../api";
import Attachments from "../components/Attachments";
import TitleBlock from "../components/TitleBlock";
import AuditDrawer from "../components/AuditDrawer";
import ChildHeader from "../components/ChildHeader";
import { formatDate } from "../util/dates";

export default function ChildComments() {
  const { id } = useParams();
  const childId = Number(id);
  const [audit, setAudit] = useState<Comment | null>(null);
  const { data } = useQuery({
    queryKey: ["comments", childId],
    queryFn: () => api.comments(childId),
    enabled: !isNaN(childId),
  });
  const rows = data || [];
  return (
    <div>
      <ChildHeader title="Teacher comments" />
      {rows.length === 0 && (
        <div className="text-gray-500">No comments yet.</div>
      )}
      <div className="space-y-3">
        {rows.map((c) => (
          <div
            key={c.id}
            className="bg-white border border-gray-200 rounded shadow-sm p-4 cursor-pointer hover:bg-gray-50"
            onClick={() => setAudit(c)}
          >
            <div className="flex items-baseline justify-between">
              <div>
                <b>{c.subject ?? "—"}</b>
                {c.normalized?.teacher && (
                  <span className="text-sm text-gray-500 ml-2">· {c.normalized.teacher}</span>
                )}
              </div>
              <div className="text-xs text-gray-500" title={c.due_or_date || c.first_seen_at || ""}>{formatDate(c.due_or_date || c.first_seen_at)}</div>
            </div>
            <div className="mt-1">
              <TitleBlock title={c.title} titleEn={c.title_en} className="text-sm text-gray-800 whitespace-pre-wrap" />
            </div>
            {c.normalized?.body && (
              <div className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">{c.normalized.body}</div>
            )}
            <Attachments items={c.attachments} />
          </div>
        ))}
      </div>
      {audit && <AuditDrawer a={audit as unknown as Assignment} onClose={() => setAudit(null)} />}
    </div>
  );
}
