import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "../api";

export default function ChildSyllabus() {
  const { id } = useParams();
  const childId = Number(id);
  const { data: child } = useQuery({
    queryKey: ["child-detail", childId],
    queryFn: () => api.childDetail(childId),
    enabled: !isNaN(childId),
  });
  const classLevel = child?.child.class_level;
  const { data: syl } = useQuery({
    queryKey: ["syllabus", classLevel],
    queryFn: () => api.syllabus(classLevel!),
    enabled: classLevel !== undefined,
  });

  const todayISO = useMemo(() => new Date().toISOString().slice(0, 10), []);

  if (!child) return <div>Loading child…</div>;
  if (!syl) return <div>Loading syllabus…</div>;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">
        <Link to={`/child/${childId}`} className="text-gray-400 hover:text-gray-700">← </Link>
        Syllabus — {child.child.display_name}
      </h2>
      <div className="text-sm text-gray-500 mb-3">
        Class {classLevel}, school year {syl.school_year || "?"} ·
        <Link to="/settings/syllabus" className="ml-2 text-blue-700 hover:underline">Calibrate cycles →</Link>
      </div>

      <div className="space-y-4">
        {syl.cycles.map((c) => {
          const isCurrent = c.start <= todayISO && todayISO <= c.end;
          return (
            <section key={c.name} className={`bg-white border rounded shadow-sm p-4 ${isCurrent ? "border-purple-400" : "border-gray-200"}`}>
              <div className="flex items-baseline justify-between">
                <h3 className="font-semibold">
                  {c.name}
                  {isCurrent && <span className="ml-2 text-xs text-purple-700 bg-purple-50 border border-purple-200 rounded px-2 py-0.5">Current</span>}
                  {c.overridden && <span className="ml-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">Overridden</span>}
                </h3>
                <div className="text-sm text-gray-600">{c.start} → {c.end}</div>
              </div>
              {c.override_note && (
                <div className="text-xs text-amber-700 mt-1">Note: {c.override_note}</div>
              )}
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                {Object.entries(c.topics_by_subject || {}).map(([subj, topics]) => (
                  <div key={subj} className="text-sm">
                    <div className="font-medium text-gray-800 mb-1">{subj}</div>
                    <ul className="space-y-0.5 text-gray-700">
                      {topics.map((t) => {
                        const st = c.topic_status?.[subj]?.[t]?.status;
                        return (
                          <li key={t} className="flex gap-2">
                            <span className="w-4 text-xs">
                              {st === "covered" ? "✅" :
                                st === "skipped" ? "⏭️" :
                                  st === "delayed" ? "⏳" :
                                    st === "in_progress" ? "🟡" : "·"}
                            </span>
                            <span>{t}</span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
