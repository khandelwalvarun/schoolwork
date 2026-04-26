/**
 * ShakyTopicsTray — Today-page card listing 2-3 topics per kid that
 * most warrant a parent-kid review conversation this week.
 *
 * Framing rules per the pedagogy research synthesis:
 *   - HARD CAP at 3 per kid. Hill & Tyson found that the strongest
 *     parent-effect comes from "academic socialization" (talking, expectations)
 *     not "doing the homework with them"; pushing 10+ items would tilt
 *     parents into the controlling pattern.
 *   - Copy says "Talk about" not "Drill" or "Practice".
 *   - Each item shows the WHY (reason chips) so the parent can lead a
 *     specific conversation instead of a generic one.
 *
 * Hidden when both kids have zero shaky topics — no empty card.
 */
import { useQuery } from "@tanstack/react-query";
import { api, ShakyTopicsResponse } from "../api";

const STATE_TONE: Record<string, string> = {
  attempted: "border-gray-300 text-gray-700",
  familiar:  "border-amber-300 text-amber-800 bg-amber-50",
  proficient: "border-blue-300 text-blue-800 bg-blue-50",
  decaying:  "border-red-300 text-red-800 bg-red-50",
};

export function ShakyTopicsTray() {
  const { data } = useQuery<ShakyTopicsResponse>({
    queryKey: ["shaky-topics"],
    queryFn: () => api.shakyTopics(3),
    staleTime: 60_000,
  });
  if (!data) return null;
  const totalItems = data.kids.reduce((s, k) => s + k.items.length, 0);
  if (totalItems === 0) return null;

  return (
    <section className="surface mb-6 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="h-section text-purple-700">Worth a chat this week</span>
        <span className="text-xs text-gray-400">
          · capped at {data.limit_per_kid} per kid · review the topic with your kid before drilling
        </span>
      </div>
      <div className="space-y-3">
        {data.kids.map((kid) =>
          kid.items.length === 0 ? null : (
            <div key={kid.child_id}>
              <div className="text-xs font-semibold text-gray-700 mb-1">
                {kid.display_name}
              </div>
              <ul className="space-y-1">
                {kid.items.map((it) => (
                  <li
                    key={`${it.child_id}-${it.subject}-${it.topic}`}
                    className="flex items-start gap-2 text-sm"
                  >
                    <span className="text-xs uppercase tracking-wider text-gray-500 w-24 flex-shrink-0 mt-0.5">
                      {it.subject}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-gray-900">{it.topic}</div>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        <span
                          className={
                            "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border " +
                            (STATE_TONE[it.state] ?? "border-gray-300 text-gray-700")
                          }
                        >
                          {it.state}
                          {it.last_score != null && ` · ${it.last_score.toFixed(0)}%`}
                        </span>
                        {it.reasons.map((r, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border border-gray-200 bg-gray-50 text-gray-600"
                          >
                            {r}
                          </span>
                        ))}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ),
        )}
      </div>
    </section>
  );
}
