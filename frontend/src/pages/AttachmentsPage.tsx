import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, AttachmentFull } from "../api";
import { formatDateShort } from "../util/dates";

function fmtSize(n: number | null | undefined): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function iconFor(filename: string): string {
  const ext = (filename.split(".").pop() || "").toLowerCase();
  if (["pdf"].includes(ext)) return "📄";
  if (["doc", "docx"].includes(ext)) return "📝";
  if (["xls", "xlsx", "csv"].includes(ext)) return "📊";
  if (["ppt", "pptx"].includes(ext)) return "📽️";
  if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return "🖼️";
  return "📎";
}

export default function AttachmentsPage() {
  const [source, setSource] = useState<string>("");
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["attachments", source],
    queryFn: () => api.attachments({ source_kind: source || undefined, limit: 500 }),
  });
  const rows = (data || []).filter((r: AttachmentFull) =>
    !q || r.filename.toLowerCase().includes(q.toLowerCase())
      || (r.item_title || "").toLowerCase().includes(q.toLowerCase())
      || (r.item_subject || "").toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3">
        <h2 className="text-2xl font-bold">Attachments</h2>
        <div className="flex gap-2 text-sm">
          <input
            className="border border-gray-300 rounded px-2 py-1"
            placeholder="filter by filename/title/subject"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="">All sources</option>
            <option value="assignment">Assignments</option>
            <option value="school_message">School messages</option>
            <option value="resource">Resources</option>
          </select>
        </div>
      </div>
      <div className="text-sm text-gray-500 mb-3">{rows.length} files</div>
      <table className="w-full text-sm bg-white border border-gray-200 rounded shadow-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-gray-500 border-b border-gray-100">
            <th className="py-2 px-3">File</th>
            <th className="py-2 px-3">Subject</th>
            <th className="py-2 px-3">From</th>
            <th className="py-2 px-3">Size</th>
            <th className="py-2 px-3">Saved</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={5} className="py-4 text-center text-gray-400">No attachments yet — run a sync.</td></tr>
          )}
          {rows.map((a) => (
            <tr key={a.id} className="border-t border-gray-100">
              <td className="py-2 px-3">
                <a
                  href={a.download_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-700 hover:text-blue-900 hover:underline inline-flex items-center gap-1"
                >
                  <span>{iconFor(a.filename)}</span>
                  <span>{a.filename}</span>
                </a>
                {a.item_title && <div className="text-xs text-gray-500 mt-0.5">↳ {a.item_title}</div>}
              </td>
              <td className="py-2 px-3 text-gray-600">{a.item_subject ?? "—"}</td>
              <td className="py-2 px-3 text-gray-600">{a.source_kind}</td>
              <td className="py-2 px-3 text-gray-600 whitespace-nowrap">{fmtSize(a.size_bytes)}</td>
              <td className="py-2 px-3 text-gray-500 whitespace-nowrap text-xs">
                {formatDateShort(a.downloaded_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
