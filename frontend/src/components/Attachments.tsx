import { AttachmentLink } from "../api";

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
  if (["zip", "rar", "7z"].includes(ext)) return "🗜️";
  if (["mp3", "wav"].includes(ext)) return "🎵";
  if (["mp4", "mov"].includes(ext)) return "🎬";
  return "📎";
}

export default function Attachments({ items }: { items: AttachmentLink[] | undefined }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {items.map((a) => (
        <a
          key={a.id}
          href={a.download_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-blue-700 hover:text-blue-900 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded px-2 py-0.5"
          title={`${a.filename}${a.size_bytes ? ` · ${fmtSize(a.size_bytes)}` : ""}`}
        >
          <span>{iconFor(a.filename)}</span>
          <span className="truncate max-w-[300px]">{a.filename}</span>
          {a.size_bytes ? <span className="text-blue-500">· {fmtSize(a.size_bytes)}</span> : null}
        </a>
      ))}
    </div>
  );
}
