import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, SpellBeeLinkedAssignment, SpellBeeList } from "../api";
import { formatDate } from "../util/dates";

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function iconFor(mime: string): string {
  if (mime.startsWith("image/")) return "🖼";
  if (mime === "application/pdf") return "📄";
  if (mime.startsWith("text/")) return "📝";
  return "📎";
}

function DropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const fs = Array.from(e.dataTransfer.files || []);
        if (fs.length) onFiles(fs);
      }}
      onClick={() => inputRef.current?.click()}
      className={
        "border-2 border-dashed rounded p-6 text-center cursor-pointer transition-colors " +
        (dragging ? "border-amber-400 bg-amber-50" : "border-gray-300 bg-gray-50 hover:bg-gray-100")
      }
    >
      <div className="text-sm text-gray-700">
        <b>Drop Spelling Bee PDFs / images here</b> or click to select.
      </div>
      <div className="text-xs text-gray-500 mt-1">
        Name them with a number (e.g. <code>list-03.pdf</code>) for correct ordering.
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.txt,.md,.docx"
        className="hidden"
        onChange={(e) => {
          const fs = Array.from(e.target.files || []);
          if (fs.length) onFiles(fs);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function ListRow({
  l,
  onRename,
  onDelete,
}: {
  l: SpellBeeList;
  onRename: (newName: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(l.filename);
  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50">
      <td className="px-3 py-2 font-mono">
        {l.number !== null ? `List ${String(l.number).padStart(2, "0")}` : "—"}
      </td>
      <td className="px-3 py-2">
        <span className="mr-1">{iconFor(l.mime_type)}</span>
        {editing ? (
          <input
            className="border border-gray-300 rounded px-1 py-0.5 text-sm w-64"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                onRename(draft);
                setEditing(false);
              } else if (e.key === "Escape") {
                setDraft(l.filename);
                setEditing(false);
              }
            }}
            autoFocus
          />
        ) : (
          <a
            href={l.download_url}
            target="_blank"
            rel="noreferrer"
            className="text-blue-700 hover:underline"
          >
            {l.filename}
          </a>
        )}
      </td>
      <td className="px-3 py-2 text-right font-mono text-gray-600">{fmtSize(l.size_bytes)}</td>
      <td className="px-3 py-2 text-right">
        <div className="inline-flex gap-1">
          <a
            href={l.download_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs border border-blue-300 rounded px-2 py-0.5 text-blue-700 hover:bg-blue-50"
          >
            View
          </a>
          {editing ? (
            <button
              onClick={() => {
                onRename(draft);
                setEditing(false);
              }}
              className="text-xs border border-green-300 rounded px-2 py-0.5 text-green-700 hover:bg-green-50"
            >
              Save
            </button>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="text-xs border border-gray-300 rounded px-2 py-0.5 text-gray-700 hover:bg-gray-50"
            >
              Rename
            </button>
          )}
          <button
            onClick={() => {
              if (confirm(`Delete ${l.filename}?`)) onDelete();
            }}
            className="text-xs border border-red-300 rounded px-2 py-0.5 text-red-700 hover:bg-red-50"
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  );
}

function LinkedAssignments({
  linked,
  lists,
}: {
  linked: SpellBeeLinkedAssignment[];
  lists: SpellBeeList[];
}) {
  if (linked.length === 0) return null;
  const byNumber = new Map<number, SpellBeeList>();
  for (const l of lists) if (l.number !== null) byNumber.set(l.number, l);
  return (
    <section className="mb-6 bg-white border border-gray-200 rounded shadow-sm p-4">
      <h3 className="font-semibold mb-2">Linked assignments</h3>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase text-gray-500 border-b border-gray-200">
          <tr>
            <th className="text-left px-2 py-1 w-24">Kid</th>
            <th className="text-left px-2 py-1 w-28">Subject</th>
            <th className="text-left px-2 py-1">Assignment</th>
            <th className="text-left px-2 py-1 w-28">Due</th>
            <th className="text-left px-2 py-1 w-48">List</th>
          </tr>
        </thead>
        <tbody>
          {linked.map((a) => {
            const match = a.detected_list_number != null ? byNumber.get(a.detected_list_number) : null;
            return (
              <tr key={a.id} className="border-t border-gray-100 align-top">
                <td className="px-2 py-1">{a.child_name}</td>
                <td className="px-2 py-1 text-gray-600">{a.subject}</td>
                <td className="px-2 py-1">
                  <div>{a.title}</div>
                  {a.title_en && a.title_en !== a.title && (
                    <div className="text-xs text-gray-500 italic">→ {a.title_en}</div>
                  )}
                </td>
                <td className="px-2 py-1 font-mono">{formatDate(a.due_or_date)}</td>
                <td className="px-2 py-1">
                  {a.detected_list_number == null && (
                    <span className="text-gray-500 italic">no list # in text</span>
                  )}
                  {a.detected_list_number != null && match && (
                    <a
                      href={match.download_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-700 hover:underline"
                    >
                      List {a.detected_list_number} · {match.filename}
                    </a>
                  )}
                  {a.detected_list_number != null && !match && (
                    <span className="text-amber-700">
                      List {a.detected_list_number} — <i>not uploaded yet</i>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export default function SpellBee() {
  const qc = useQueryClient();
  const { data: lists, isLoading } = useQuery<SpellBeeList[]>({
    queryKey: ["spellbee-lists"],
    queryFn: api.spellbeeLists,
  });
  const { data: linked } = useQuery<SpellBeeLinkedAssignment[]>({
    queryKey: ["spellbee-linked"],
    queryFn: api.spellbeeLinkedAssignments,
  });

  const upload = useMutation({
    mutationFn: (files: File[]) => api.spellbeeUpload(files),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["spellbee-lists"] });
      if (r.errors.length > 0) {
        alert(
          "Some files were rejected:\n" +
            r.errors.map((e) => `• ${e.filename}: ${e.error}`).join("\n"),
        );
      }
    },
  });
  const del = useMutation({
    mutationFn: (filename: string) => api.spellbeeDelete(filename),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["spellbee-lists"] }),
  });
  const rename = useMutation({
    mutationFn: ({ filename, newName }: { filename: string; newName: string }) =>
      api.spellbeeRename(filename, newName),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["spellbee-lists"] }),
  });

  const missingLists = useMemo(() => {
    if (!linked || !lists) return [];
    const have = new Set(lists.map((l) => l.number).filter((n): n is number => n != null));
    const want = new Set<number>();
    for (const a of linked) if (a.detected_list_number != null) want.add(a.detected_list_number);
    return [...want].filter((n) => !have.has(n)).sort((a, b) => a - b);
  }, [linked, lists]);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">🐝 Spelling Bee</h2>
      <p className="text-sm text-gray-600 mb-4">
        Upload the word-list files here. Filenames that contain a number
        (e.g. <code>list-03.pdf</code>) are sorted and cross-referenced to
        assignments automatically. Everything lives in{" "}
        <code className="text-xs bg-gray-100 border border-gray-200 rounded px-1 py-0.5">
          data/spellbee/
        </code>
        .
      </p>

      <div className="mb-4">
        <DropZone onFiles={(fs) => upload.mutate(fs)} />
        {upload.isPending && <div className="text-xs text-gray-500 mt-2">Uploading…</div>}
      </div>

      {linked && lists && <LinkedAssignments linked={linked} lists={lists} />}

      {missingLists.length > 0 && (
        <div className="mb-4 bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-900">
          <b>Missing:</b> assignments reference{" "}
          {missingLists.map((n) => `List ${n}`).join(", ")} but no matching file
          has been uploaded. Drop those files above.
        </div>
      )}

      {isLoading && <div className="text-sm text-gray-500">Loading…</div>}
      {lists && lists.length === 0 && (
        <div className="bg-gray-50 border border-gray-200 rounded p-4 text-sm text-gray-700">
          No lists yet. Use the drop zone above, or copy files into{" "}
          <code className="text-xs">data/spellbee/</code> manually.{" "}
          <Link to="/" className="text-blue-700 hover:underline">← back home</Link>
        </div>
      )}

      {lists && lists.length > 0 && (
        <section className="bg-white border border-gray-200 rounded shadow-sm">
          <div className="px-3 py-2 border-b border-gray-200 text-xs uppercase text-gray-500 font-semibold">
            Uploaded lists
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 border-b border-gray-200">
              <tr>
                <th className="text-left px-3 py-2 w-24">#</th>
                <th className="text-left px-3 py-2">File</th>
                <th className="text-right px-3 py-2 w-24">Size</th>
                <th className="text-right px-3 py-2 w-52">Actions</th>
              </tr>
            </thead>
            <tbody>
              {lists.map((l) => (
                <ListRow
                  key={l.filename}
                  l={l}
                  onRename={(newName) => rename.mutate({ filename: l.filename, newName })}
                  onDelete={() => del.mutate(l.filename)}
                />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
