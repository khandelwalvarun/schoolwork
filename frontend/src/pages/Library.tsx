/**
 * Library — parent-uploaded reference files (textbook PDFs, study
 * material, scanned newsletters) classified by Claude.
 *
 * Layout:
 *   - Drop zone at the top (drag-drop or click to browse)
 *   - Filter strip (kid · kind · subject)
 *   - Card grid: title + kind/subject chips + summary + keywords + actions
 *
 * Classification fires asynchronously after upload; rows arrive on the
 * list with `llm_kind: null` and the card shows a "classifying…" state
 * for a few seconds, then the badges fill in on the next refresh.
 */
import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Child, LibraryFile } from "../api";

const KIND_TONE: Record<string, string> = {
  textbook:      "border-blue-300 text-blue-800 bg-blue-50",
  workbook:      "border-cyan-300 text-cyan-800 bg-cyan-50",
  reference:     "border-indigo-300 text-indigo-800 bg-indigo-50",
  study_guide:   "border-purple-300 text-purple-800 bg-purple-50",
  newsletter:    "border-gray-300 text-gray-800 bg-gray-50",
  syllabus:      "border-amber-300 text-amber-800 bg-amber-50",
  test_paper:    "border-red-300 text-red-800 bg-red-50",
  scanned_notes: "border-emerald-300 text-emerald-800 bg-emerald-50",
  project:       "border-pink-300 text-pink-800 bg-pink-50",
  other:         "border-gray-300 text-gray-700 bg-white",
};

function fmtSize(bytes: number | null): string {
  if (bytes == null) return "?";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtUploaded(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

export default function Library() {
  const qc = useQueryClient();
  const [childFilter, setChildFilter] = useState<number | "all">("all");
  const [kindFilter, setKindFilter] = useState<string | "all">("all");
  const [uploadKidId, setUploadKidId] = useState<number | "shared">("shared");
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: kids } = useQuery({
    queryKey: ["children"],
    queryFn: () => api.children(),
    staleTime: 5 * 60_000,
  });

  const { data, isLoading } = useQuery<LibraryFile[]>({
    queryKey: ["library", childFilter, kindFilter],
    queryFn: () =>
      api.libraryList(
        childFilter === "all" ? undefined : childFilter,
        kindFilter === "all" ? undefined : kindFilter,
      ),
    staleTime: 30_000,
    refetchInterval: (q) => {
      // Poll every 8s while any row is still classifying.
      const arr = q.state.data as LibraryFile[] | undefined;
      if (!arr) return false;
      const pending = arr.some((r) => !r.llm_processed_at);
      return pending ? 8_000 : false;
    },
  });

  const upload = useMutation({
    mutationFn: (files: File[]) =>
      api.libraryUpload(
        files,
        uploadKidId === "shared" ? undefined : uploadKidId,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library"] });
    },
  });

  const del = useMutation({
    mutationFn: (id: number) => api.libraryDelete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["library"] }),
  });

  const reclassify = useMutation({
    mutationFn: (id: number) => api.libraryReclassify(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["library"] }),
  });

  const rows = data ?? [];

  // Distinct kinds present in the data, for the filter strip.
  const kinds = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) if (r.llm_kind) s.add(r.llm_kind);
    return Array.from(s).sort();
  }, [rows]);

  return (
    <div className="pb-12">
      <h2 className="text-2xl font-bold mb-2">Library</h2>
      <p className="text-sm text-gray-600 mb-4">
        Drop in textbook PDFs, scanned worksheets, syllabus copies — Claude
        reads each one and classifies kind, subject, class level, and a
        short summary. Files stay on this machine.
      </p>

      {/* Upload area */}
      <section className="surface mb-6 p-5">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <span className="text-sm text-gray-600">Tag uploads to:</span>
          <select
            className="text-sm border border-gray-300 rounded px-2 py-1"
            value={uploadKidId === "shared" ? "shared" : String(uploadKidId)}
            onChange={(e) =>
              setUploadKidId(
                e.target.value === "shared" ? "shared" : Number(e.target.value),
              )
            }
          >
            <option value="shared">Shared (no kid)</option>
            {(kids as Child[] | undefined)?.map((k) => (
              <option key={k.id} value={k.id}>{k.display_name}</option>
            ))}
          </select>
        </div>
        <input
          ref={fileRef}
          type="file"
          multiple
          className="hidden"
          accept="application/pdf,text/*,image/*,.docx,.doc,.xlsx,.xls"
          onChange={(e) => {
            const files = Array.from(e.target.files || []);
            if (files.length > 0) upload.mutate(files);
            if (fileRef.current) fileRef.current.value = "";
          }}
        />
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const files = Array.from(e.dataTransfer.files || []);
            if (files.length > 0) upload.mutate(files);
          }}
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded p-6 text-center hover:bg-gray-50 cursor-pointer text-sm text-gray-600"
        >
          {upload.isPending
            ? "Uploading…"
            : "Drop files here, or click to browse · PDF / text / images / DOCX up to 50 MB"}
        </div>
        {upload.isError && (
          <div className="text-xs text-red-700 mt-2">
            Upload failed: {String(upload.error)}
          </div>
        )}
      </section>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 text-xs flex-wrap">
        <span className="text-gray-500">Filter:</span>
        <select
          className="border border-gray-300 rounded px-2 py-1"
          value={childFilter === "all" ? "all" : String(childFilter)}
          onChange={(e) =>
            setChildFilter(e.target.value === "all" ? "all" : Number(e.target.value))
          }
        >
          <option value="all">All kids</option>
          {(kids as Child[] | undefined)?.map((k) => (
            <option key={k.id} value={k.id}>{k.display_name}</option>
          ))}
        </select>
        <select
          className="border border-gray-300 rounded px-2 py-1"
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
        >
          <option value="all">All kinds</option>
          {kinds.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <span className="ml-auto text-gray-400">
          {rows.length} file{rows.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="text-gray-400">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="surface p-6 text-center text-sm text-gray-500">
          Nothing in the library yet. Drop a textbook PDF or worksheet above to
          get started.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {rows.map((r) => {
            const tone = KIND_TONE[r.llm_kind || "other"] || KIND_TONE.other;
            const classifying = !r.llm_processed_at;
            const failed = !!r.llm_error;
            const kid = (kids as Child[] | undefined)?.find(
              (k) => k.id === r.child_id,
            );
            return (
              <article
                key={r.id}
                className="surface p-4 flex flex-col gap-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <a
                    href={`/api/library/${r.id}/download`}
                    target="_blank"
                    rel="noreferrer"
                    className="font-semibold text-gray-900 hover:underline truncate flex-1"
                    title={r.original_filename || r.filename}
                  >
                    {r.original_filename || r.filename}
                  </a>
                  <button
                    type="button"
                    onClick={() => del.mutate(r.id)}
                    className="text-gray-400 hover:text-red-600 text-base leading-none flex-shrink-0"
                    aria-label="Delete"
                  >
                    ×
                  </button>
                </div>

                <div className="flex items-center gap-2 flex-wrap text-[11px]">
                  {r.llm_kind && (
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded border ${tone}`}>
                      {r.llm_kind.replace("_", " ")}
                    </span>
                  )}
                  {r.llm_subject && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded border border-gray-200 bg-white text-gray-700">
                      {r.llm_subject}
                    </span>
                  )}
                  {r.llm_class_level != null && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded border border-gray-200 bg-white text-gray-700">
                      Class {r.llm_class_level}
                    </span>
                  )}
                  {kid && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded border border-purple-200 bg-purple-50 text-purple-800">
                      {kid.display_name}
                    </span>
                  )}
                  {classifying && (
                    <span className="text-gray-500 italic">classifying…</span>
                  )}
                  {failed && (
                    <span className="text-red-700">
                      classify failed
                      <button
                        type="button"
                        onClick={() => reclassify.mutate(r.id)}
                        className="ml-1 underline"
                      >
                        retry
                      </button>
                    </span>
                  )}
                </div>

                {r.llm_summary && (
                  <p className="text-sm text-gray-700 leading-snug">
                    {r.llm_summary}
                  </p>
                )}

                {r.llm_keywords.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {r.llm_keywords.map((kw) => (
                      <span
                        key={kw}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border border-gray-200 bg-gray-50 text-gray-600"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                )}

                <div className="text-[10px] text-gray-400 flex items-center gap-2">
                  <span>{fmtSize(r.size_bytes)}</span>
                  <span>·</span>
                  <span>{fmtUploaded(r.uploaded_at)}</span>
                  {r.llm_error && !failed && (
                    <>
                      <span>·</span>
                      <span className="text-amber-700">
                        {r.llm_error.slice(0, 60)}
                      </span>
                    </>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
