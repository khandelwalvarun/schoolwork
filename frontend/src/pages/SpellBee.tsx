import { useQuery } from "@tanstack/react-query";
import { api, SpellBeeList } from "../api";

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

export default function SpellBee() {
  const { data, isLoading } = useQuery<SpellBeeList[]>({
    queryKey: ["spellbee-lists"],
    queryFn: api.spellbeeLists,
  });

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">🐝 Spelling Bee</h2>
      <p className="text-sm text-gray-600 mb-4">
        Word lists live in{" "}
        <code className="text-xs bg-gray-100 border border-gray-200 rounded px-1 py-0.5">data/spellbee/</code>
        . Drop a PDF / image / text file named like{" "}
        <code className="text-xs bg-gray-100 border border-gray-200 rounded px-1 py-0.5">list-01.pdf</code>{" "}
        and it will appear here automatically.
      </p>

      {isLoading && <div className="text-sm text-gray-500">Loading…</div>}
      {data && data.length === 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded p-4 text-sm text-amber-800">
          No lists yet. Copy your Spelling Bee PDFs/images into{" "}
          <code className="text-xs">data/spellbee/</code>. Filenames that contain a
          number (e.g. <code>list-03.pdf</code>) will be ordered by that number.
        </div>
      )}

      {data && data.length > 0 && (
        <section className="bg-white border border-gray-200 rounded shadow-sm">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 border-b border-gray-200">
              <tr>
                <th className="text-left px-3 py-2 w-20">#</th>
                <th className="text-left px-3 py-2">File</th>
                <th className="text-right px-3 py-2 w-28">Size</th>
                <th className="text-right px-3 py-2 w-24">Open</th>
              </tr>
            </thead>
            <tbody>
              {data.map((l) => (
                <tr key={l.filename} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 font-mono">
                    {l.number !== null ? `List ${String(l.number).padStart(2, "0")}` : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span className="mr-1">{iconFor(l.mime_type)}</span>
                    <a
                      href={l.download_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-700 hover:underline"
                    >
                      {l.filename}
                    </a>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-gray-600">
                    {fmtSize(l.size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <a
                      href={l.download_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs border border-blue-300 rounded px-2 py-0.5 text-blue-700 hover:bg-blue-50"
                    >
                      View
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
