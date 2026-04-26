/**
 * ShakyTopicsTray — Today-page card listing topics that warrant a
 * parent-kid review conversation.
 *
 * No artificial cap — the parent sees the full list and dismisses
 * specific items per row. Dismissals persist in ui_prefs under
 * `shaky_dismissed[child_id]` keyed by `subject::topic`.
 *
 * UX:
 *   - Each row has a checkbox on the left. Checking it dismisses the
 *     row; the row fades out and disappears from the visible list.
 *   - A small footer shows how many are hidden + a "Show hidden"
 *     toggle that reveals dismissed rows so they can be un-dismissed
 *     by unchecking.
 *   - Tray hides entirely when both kids have zero (visible + hidden) items.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ShakyTopic, ShakyTopicsResponse } from "../api";
import { useUiPrefs } from "./useUiPrefs";

const STATE_TONE: Record<string, string> = {
  attempted: "border-gray-300 text-gray-700",
  familiar:  "border-amber-300 text-amber-800 bg-amber-50",
  proficient: "border-blue-300 text-blue-800 bg-blue-50",
  decaying:  "border-red-300 text-red-800 bg-red-50",
};

const dismissKey = (it: ShakyTopic) => `${it.subject}::${it.topic}`;

/** Phase 15: derive language from subject. Kept in lockstep with the
 *  backend's services/language.py + the syllabus page's helper. */
function languageOf(subject: string | null | undefined): "en" | "hi" | "sa" | null {
  if (!subject) return null;
  const s = subject.toLowerCase();
  if (s.includes("sanskrit")) return "sa";
  if (s.includes("hindi")) return "hi";
  if (s.includes("english")) return "en";
  return null;
}

const LANG_CHIP: Record<"en" | "hi" | "sa", { label: string; tone: string }> = {
  en: { label: "EN", tone: "border-blue-300 text-blue-800 bg-blue-50" },
  hi: { label: "हिन्दी", tone: "border-amber-300 text-amber-800 bg-amber-50" },
  sa: { label: "संस्कृत", tone: "border-purple-300 text-purple-800 bg-purple-50" },
};

export function ShakyTopicsTray() {
  const { data } = useQuery<ShakyTopicsResponse>({
    queryKey: ["shaky-topics"],
    queryFn: () => api.shakyTopics(),
    staleTime: 60_000,
  });
  const { prefs, setShakyDismissed } = useUiPrefs();
  const [showHidden, setShowHidden] = useState(false);

  const dismissedByKid = prefs.shaky_dismissed ?? {};

  const setDismissed = (childId: number, key: string, dismissed: boolean) => {
    const cur = new Set(dismissedByKid[String(childId)] ?? []);
    if (dismissed) cur.add(key);
    else cur.delete(key);
    setShakyDismissed({
      ...dismissedByKid,
      [String(childId)]: [...cur],
    });
  };

  const counts = useMemo(() => {
    if (!data) return { visible: 0, hidden: 0 };
    let visible = 0;
    let hidden = 0;
    for (const kid of data.kids) {
      const ds = new Set(dismissedByKid[String(kid.child_id)] ?? []);
      for (const it of kid.items) {
        if (ds.has(dismissKey(it))) hidden++;
        else visible++;
      }
    }
    return { visible, hidden };
  }, [data, dismissedByKid]);

  if (!data) return null;
  if (counts.visible === 0 && counts.hidden === 0) return null;
  if (counts.visible === 0 && !showHidden) {
    // Everything dismissed — collapsed surface with restore link.
    return (
      <section className="surface mb-6 p-3 text-xs text-gray-500 flex items-center justify-between">
        <span>All shaky topics dismissed.</span>
        <button
          onClick={() => setShowHidden(true)}
          className="text-blue-700 hover:underline"
        >
          Show {counts.hidden} hidden
        </button>
      </section>
    );
  }

  return (
    <section className="surface mb-6 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="h-section text-purple-700">Worth a chat this week</span>
        <span className="text-xs text-gray-400">
          · {counts.visible} item{counts.visible === 1 ? "" : "s"}
          {counts.hidden > 0 && ` · ${counts.hidden} hidden`}
          · review the topic with your kid before drilling
        </span>
      </div>
      <div className="space-y-3">
        {data.kids.map((kid) => {
          const ds = new Set(dismissedByKid[String(kid.child_id)] ?? []);
          const visibleItems = kid.items.filter((it) =>
            showHidden ? true : !ds.has(dismissKey(it)),
          );
          if (visibleItems.length === 0) return null;
          return (
            <div key={kid.child_id}>
              <div className="text-xs font-semibold text-gray-700 mb-1">
                {kid.display_name}
              </div>
              <ul className="space-y-1">
                {visibleItems.map((it) => {
                  const k = dismissKey(it);
                  const dismissed = ds.has(k);
                  return (
                    <li
                      key={k}
                      className={
                        "flex items-start gap-2 text-sm " +
                        (dismissed ? "opacity-50" : "")
                      }
                    >
                      <input
                        type="checkbox"
                        checked={dismissed}
                        onChange={(e) =>
                          setDismissed(it.child_id, k, e.target.checked)
                        }
                        title={dismissed ? "Restore" : "Dismiss this item"}
                        aria-label={dismissed ? "Restore" : "Dismiss"}
                        className="mt-1 h-4 w-4 accent-blue-700 cursor-pointer"
                      />
                      <span className="text-xs uppercase tracking-wider text-gray-500 w-24 flex-shrink-0 mt-0.5">
                        {it.subject}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className={"text-gray-900 " + (dismissed ? "line-through" : "")}>
                          {it.topic}
                        </div>
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
                          {(() => {
                            const lc = languageOf(it.subject);
                            if (!lc) return null;
                            const meta = LANG_CHIP[lc];
                            return (
                              <span
                                className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${meta.tone}`}
                              >
                                {meta.label}
                              </span>
                            );
                          })()}
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
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
      {counts.hidden > 0 && (
        <div className="mt-3 pt-2 border-t border-[color:var(--line-soft)] text-xs text-gray-500">
          <button
            onClick={() => setShowHidden((v) => !v)}
            className="text-blue-700 hover:underline"
          >
            {showHidden ? "Hide dismissed" : `Show ${counts.hidden} dismissed`}
          </button>
        </div>
      )}
    </section>
  );
}
