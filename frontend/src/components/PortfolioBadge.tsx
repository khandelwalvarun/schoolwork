/**
 * PortfolioBadge — per-topic mini surface that:
 *   - shows a paperclip count when ≥ 1 portfolio item exists
 *   - opens a popover listing the items + a [+] file picker
 *   - lets you delete an item with a small × button
 *
 * Sized to fit inline next to a syllabus topic row. The picker accepts
 * images (jpg/png/webp/heic) and PDFs; the backend caps each file at
 * 10 MB and dedups by SHA-256.
 *
 * Built deliberately spartan — phones-out-and-snap is the canonical
 * use case (kid finished a poster; parent photographs and tags).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, PortfolioItem } from "../api";

type Props = {
  childId: number;
  subject: string;
  topic: string;
};

function fmtSize(bytes: number | null): string {
  if (bytes == null) return "?";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function PortfolioBadge({ childId, subject, topic }: Props) {
  const [open, setOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<PortfolioItem[]>({
    queryKey: ["portfolio", childId, subject, topic],
    queryFn: () => api.portfolioList(childId, subject, topic),
    staleTime: 30_000,
  });

  const upload = useMutation({
    mutationFn: (files: File[]) =>
      api.portfolioUpload(childId, subject, topic, files),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio", childId, subject, topic] });
    },
  });

  const del = useMutation({
    mutationFn: (id: number) => api.portfolioDelete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio", childId, subject, topic] });
    },
  });

  const count = data?.length ?? 0;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        className={
          "inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[10px] border " +
          (count > 0
            ? "border-purple-300 text-purple-800 bg-purple-50"
            : "border-gray-200 text-gray-400 hover:bg-gray-50")
        }
        onClick={() => setOpen((v) => !v)}
        title={
          count > 0
            ? `${count} portfolio item${count === 1 ? "" : "s"}`
            : "Add a portfolio item (photo, scan, drawing)"
        }
        aria-expanded={open}
      >
        <span aria-hidden>📎</span>
        {count > 0 && <span>{count}</span>}
      </button>
      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute right-0 mt-1 z-50 w-72 surface p-3 shadow-lg border border-gray-200 text-xs">
            <div className="flex items-baseline justify-between mb-2">
              <span className="font-semibold text-gray-700">Portfolio</span>
              <span className="text-gray-400 truncate ml-2">{topic}</span>
            </div>
            {isLoading ? (
              <div className="h-12 skeleton rounded" />
            ) : count === 0 ? (
              <div className="text-gray-500 italic">
                No items yet. Photos, scans, or PDFs welcome.
              </div>
            ) : (
              <ul className="space-y-1">
                {(data ?? []).map((it) => (
                  <li
                    key={it.id}
                    className="flex items-center gap-2 text-xs"
                  >
                    <a
                      href={`/api/attachments/${it.id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-700 hover:underline truncate flex-1"
                      title={it.filename}
                    >
                      {it.filename}
                    </a>
                    <span className="text-gray-400 flex-shrink-0">
                      {fmtSize(it.size_bytes)}
                    </span>
                    <button
                      type="button"
                      className="text-red-700 hover:underline flex-shrink-0"
                      disabled={del.isPending}
                      onClick={() => del.mutate(it.id)}
                      aria-label="Delete portfolio item"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-3 pt-2 border-t border-gray-200">
              <input
                ref={fileRef}
                type="file"
                accept="image/*,application/pdf"
                multiple
                className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  if (files.length > 0) upload.mutate(files);
                  if (fileRef.current) fileRef.current.value = "";
                }}
              />
              <button
                type="button"
                className="text-blue-700 hover:underline disabled:opacity-50"
                disabled={upload.isPending}
                onClick={() => fileRef.current?.click()}
              >
                {upload.isPending ? "uploading…" : "+ add files"}
              </button>
              {upload.isError && (
                <span className="ml-2 text-red-700">
                  upload failed
                </span>
              )}
            </div>
          </div>
        </>
      )}
    </span>
  );
}
