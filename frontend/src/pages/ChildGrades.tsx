import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, Assignment, AttachmentLink, GradeTrend } from "../api";
import { useState } from "react";
import Attachments from "../components/Attachments";
import TitleBlock from "../components/TitleBlock";
import AuditDrawer from "../components/AuditDrawer";
import ChildHeader from "../components/ChildHeader";
import { SortableTH, useSortable } from "../components/useSortable";
import { formatDDMMMYY, formatDDMMMYYTime } from "../util/dates";

type GradeRow = {
  id: number;
  subject: string | null;
  title: string | null;
  title_en?: string | null;
  graded_date?: string | null;
  grade_pct?: number | null;
  score_text?: string | null;
  first_seen_at?: string | null;
  attachments?: AttachmentLink[];
  normalized?: Record<string, unknown>;
};

export default function ChildGrades() {
  const { id } = useParams();
  const childId = Number(id);
  const [subject, setSubject] = useState<string | undefined>();
  const [annotate, setAnnotate] = useState(false);
  const [audit, setAudit] = useState<Assignment | null>(null);

  const { data: trends } = useQuery<GradeTrend[]>({
    queryKey: ["grade-trends", childId, annotate],
    queryFn: () => (annotate ? api.gradeTrendsAnnotated(childId) : api.gradeTrends(childId)),
    enabled: !isNaN(childId),
  });

  const { data: grades } = useQuery({
    queryKey: ["grades", childId, subject],
    queryFn: () => api.grades(childId, subject),
    enabled: !isNaN(childId),
  });

  const rows = (grades || []) as GradeRow[];

  const sort = useSortable<GradeRow>(rows, "graded_date", "desc", (g, key) => {
    switch (key) {
      case "graded_date":   return g.graded_date ?? null;
      case "subject":       return g.subject ?? null;
      case "title":         return (g.title ?? null);
      case "score_text":    return g.score_text ?? null;
      case "grade_pct":     return g.grade_pct ?? null;
      case "first_seen_at": return g.first_seen_at ?? null;
      default:              return null;
    }
  });

  return (
    <div>
      <ChildHeader title="Grades" />
      <div className="flex justify-end mb-4">
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={annotate}
            onChange={(e) => setAnnotate(e.target.checked)}
          />
          LLM annotation (syllabus-aware)
        </label>
      </div>

      {trends && trends.length > 0 && (
        <section className="mb-6 bg-white border border-gray-200 rounded shadow-sm p-4">
          <h3 className="font-semibold text-purple-700 mb-3">📊 Trends</h3>
          <div className="space-y-2 text-sm">
            {trends.map((t) => (
              <div
                key={t.subject}
                className="flex items-start gap-3 border-t border-gray-100 pt-2 cursor-pointer"
                onClick={() => setSubject(t.subject === subject ? undefined : t.subject)}
              >
                <div className="w-28 font-medium">{t.subject}</div>
                <div className="font-mono w-24">{t.sparkline}</div>
                <div className="text-lg w-6">{t.arrow}</div>
                <div className="w-24">latest <b>{t.latest.toFixed(0)}%</b></div>
                <div className="text-gray-500 w-32">avg {t.avg.toFixed(0)}% (n={t.count})</div>
                {t.annotation && (
                  <div className="flex-1 text-gray-700 italic">{t.annotation}</div>
                )}
              </div>
            ))}
          </div>
          <div className="text-xs text-gray-500 mt-3">Click a subject to filter the grade list below.</div>
        </section>
      )}

      <section className="bg-white border border-gray-200 rounded shadow-sm p-4">
        <h3 className="font-semibold mb-2">
          All grades {subject && <span className="text-gray-500 font-normal">· {subject}</span>}
          {subject && (
            <button className="ml-2 text-xs text-blue-700 hover:underline" onClick={() => setSubject(undefined)}>clear</button>
          )}
        </h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase border-b border-[color:var(--line-soft)]">
              <SortableTH label="Graded"     k="graded_date"   s={sort} />
              <SortableTH label="Detected"   k="first_seen_at" s={sort} />
              <SortableTH label="Subject"    k="subject"       s={sort} />
              <SortableTH label="Assignment" k="title"         s={sort} />
              <SortableTH label="Score"      k="score_text"    s={sort} />
              <SortableTH label="%"          k="grade_pct"     s={sort} align="right" />
            </tr>
          </thead>
          <tbody>
            {sort.sorted.length === 0 && (
              <tr><td colSpan={6} className="py-4 text-center text-gray-400">No grades yet.</td></tr>
            )}
            {sort.sorted.map((g) => {
              const hasAttach = (g.attachments?.length ?? 0) > 0;
              return (
                <tr
                  key={g.id}
                  className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer align-top"
                  onClick={() => setAudit(g as unknown as Assignment)}
                >
                  <td className="py-1 px-2 whitespace-nowrap align-top font-mono text-gray-800"
                      title={g.graded_date ?? ""}>
                    {formatDDMMMYY(g.graded_date)}
                  </td>
                  <td className="py-1 px-2 whitespace-nowrap align-top font-mono text-gray-500 text-xs"
                      title={g.first_seen_at ?? "first seen by scraper"}>
                    {formatDDMMMYYTime(g.first_seen_at)}
                  </td>
                  <td className="py-1 px-2 align-top">{g.subject}</td>
                  <td className="py-1 px-2 align-top">
                    <TitleBlock title={g.title} titleEn={g.title_en} className="text-sm" />
                    {hasAttach && <Attachments items={g.attachments} />}
                  </td>
                  <td className="py-1 px-2 text-gray-600 align-top">{g.score_text ?? "—"}</td>
                  <td className="py-1 px-2 font-mono align-top text-right">
                    {g.grade_pct !== null && g.grade_pct !== undefined ? `${Number(g.grade_pct).toFixed(0)}%` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
    </div>
  );
}
