import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, ResourceFile, ResourcesResponse } from "../api";
import { Skeleton, SkeletonList } from "../components/Skeleton";
import { Tabs, type TabItem } from "../components/Tabs";

const CATEGORY_LABELS: Record<string, string> = {
  news: "News / Newsletters",
  misc: "Misc",
  schedules: "Time tables & schedules",
  assessments: "Assessments & exams",
  general: "General (handbook, forms)",
  spellbee: "🐝 Spell Bee",
  reading: "Reading / book lists",
  syllabus: "Syllabus PDFs",
};

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtWhen(epoch: number): string {
  const d = new Date(epoch * 1000);
  const now = Date.now();
  const diff = (now - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" });
}

function iconFor(mime: string): string {
  if (mime.startsWith("image/")) return "🖼";
  if (mime === "application/pdf") return "📄";
  if (mime.includes("spreadsheet")) return "📊";
  if (mime.includes("word")) return "📝";
  if (mime.includes("presentation")) return "📽";
  return "📎";
}

function FileRow({ f }: { f: ResourceFile }) {
  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50">
      <td className="px-3 py-1.5">
        <a
          href={f.download_url}
          target="_blank"
          rel="noreferrer"
          className="text-blue-700 hover:underline"
        >
          <span className="mr-1">{iconFor(f.mime_type)}</span>
          {f.filename}
        </a>
      </td>
      <td className="px-3 py-1.5 font-mono text-xs text-gray-600 text-right whitespace-nowrap">
        {fmtSize(f.size_bytes)}
      </td>
      <td className="px-3 py-1.5 text-xs text-gray-500 text-right whitespace-nowrap">
        {fmtWhen(f.modified_at)}
      </td>
    </tr>
  );
}

function CategorySection({ title, files }: { title: string; files: ResourceFile[] }) {
  const [open, setOpen] = useState(true);
  if (files.length === 0) return null;
  const label = CATEGORY_LABELS[title] ?? title;
  return (
    <section className="mb-4 bg-white border border-gray-200 rounded shadow-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-3 py-2 flex items-center justify-between text-left border-b border-gray-200 bg-gray-50 hover:bg-gray-100"
      >
        <div className="font-semibold text-sm">
          {label}{" "}
          <span className="text-gray-500 font-normal">· {files.length}</span>
        </div>
        <span className="text-gray-400 text-xs">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <table className="w-full text-sm">
          <tbody>
            {files.map((f) => (
              <FileRow key={f.scope + f.category + f.filename + (f.child_id ?? "")} f={f} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default function Resources() {
  const { data, isLoading } = useQuery<ResourcesResponse>({
    queryKey: ["resources"],
    queryFn: () => api.resources(),
  });
  const [activeTab, setActiveTab] = useState<"schoolwide" | number>("schoolwide");

  const totals = useMemo(() => {
    if (!data) return { schoolwide: 0, kids: {} as Record<number, number> };
    const sw = Object.values(data.schoolwide).reduce((n, arr) => n + arr.length, 0);
    const kids: Record<number, number> = {};
    for (const k of data.kids) {
      kids[k.child_id] = Object.values(k.by_category).reduce((n, arr) => n + arr.length, 0);
    }
    return { schoolwide: sw, kids };
  }, [data]);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">Resources</h2>
      <p className="text-sm text-gray-600 mb-4">
        Everything from the school portal's landing page — newsletters, time
        tables, book lists, spelling lists, the handbook, homework schedules.
        Refreshed weekly so this is always up to date.
      </p>

      {isLoading && (
        <div className="space-y-4">
          <div className="flex gap-2 mb-4 border-b border-gray-200">
            <Skeleton w={120} h={20} className="mb-2" />
            <Skeleton w={120} h={20} className="mb-2" />
            <Skeleton w={120} h={20} className="mb-2" />
          </div>
          <SkeletonList rows={6} />
          <SkeletonList rows={4} />
        </div>
      )}
      {data && (
        <>
          <Tabs
            tone="purple"
            active={activeTab as string | number}
            onChange={(k) => setActiveTab(k as "schoolwide" | number)}
            items={[
              { key: "schoolwide" as const, label: "School-wide", count: totals.schoolwide },
              ...data.kids.map<TabItem<number>>((k) => ({
                key: k.child_id,
                label: `${k.display_name} · ${k.kid_slug.split("_")[1] ?? ""}`,
                count: totals.kids[k.child_id] ?? 0,
              })),
            ]}
          />

          {activeTab === "schoolwide" &&
            Object.entries(data.schoolwide)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([cat, files]) => <CategorySection key={cat} title={cat} files={files} />)}

          {typeof activeTab === "number" &&
            data.kids
              .filter((k) => k.child_id === activeTab)
              .flatMap((k) =>
                Object.entries(k.by_category)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([cat, files]) => (
                    <CategorySection key={cat} title={cat} files={files} />
                  )),
              )}

          {data.kids.length === 0 && activeTab === "schoolwide" &&
            totals.schoolwide === 0 && (
              <div className="bg-gray-50 border border-gray-200 rounded p-6 text-center">
                <div className="text-base font-medium text-gray-800 mb-1">
                  No resources here yet
                </div>
                <div className="text-sm text-gray-600">
                  Files will appear here automatically after the next sync.
                </div>
              </div>
            )}
        </>
      )}
    </div>
  );
}
