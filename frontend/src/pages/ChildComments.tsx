import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function ChildComments() {
  const { id } = useParams();
  const childId = Number(id);
  const { data } = useQuery({
    queryKey: ["comments", childId],
    queryFn: () => api.comments(childId),
    enabled: !isNaN(childId),
  });
  const rows = data || [];
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">
        <Link to={`/child/${childId}`} className="text-gray-400 hover:text-gray-700">← </Link>
        Teacher comments
      </h2>
      {rows.length === 0 && (
        <div className="text-gray-500">No comments yet.</div>
      )}
      <div className="space-y-3">
        {rows.map((c) => (
          <div key={c.id} className="bg-white border border-gray-200 rounded shadow-sm p-4">
            <div className="flex items-baseline justify-between">
              <div>
                <b>{c.subject ?? "—"}</b>
                {c.normalized?.teacher && (
                  <span className="text-sm text-gray-500 ml-2">· {c.normalized.teacher}</span>
                )}
              </div>
              <div className="text-xs text-gray-500">{c.due_or_date || c.first_seen_at}</div>
            </div>
            <div className="text-sm text-gray-800 mt-1 whitespace-pre-wrap">{c.title}</div>
            {c.normalized?.body && (
              <div className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">{c.normalized.body}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
