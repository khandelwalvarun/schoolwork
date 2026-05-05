/**
 * ShakyTopicsTray — Today-page strip listing topics that warrant a
 * parent-kid review conversation.
 *
 * Migrated to the shared Tray primitive (components/Tray.tsx) so it
 * shares header chrome with AnomalyTray + WorthAChatTray. Tray
 * handles expand/collapse + tone vocab; this file is just the row
 * renderer plus dismissal state.
 *
 * Dismissals persist in ui_prefs under `shaky_dismissed[child_id]`
 * keyed by `subject::topic`.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ShakyTopic, ShakyTopicsResponse } from "../api";
import { useUiPrefs } from "./useUiPrefs";
import { Tray, trayLineClass } from "./Tray";

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

  // All items dismissed → tiny restore link, no surface card.
  if (counts.visible === 0 && !showHidden) {
    return (
      <div className="mb-4 text-meta text-gray-500 flex items-center gap-2">
        <span>✓ All shaky topics dismissed.</span>
        <button
          onClick={() => setShowHidden(true)}
          className="text-blue-700 hover:underline"
        >
          show {counts.hidden} hidden
        </button>
      </div>
    );
  }

  const summary = [
    counts.hidden > 0 ? `${counts.hidden} hidden` : null,
    "review with your kid before drilling",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Tray
      title="📚 Worth a chat this week"
      count={counts.visible}
      summary={summary}
      tone="purple"
      rightSlot={
        counts.hidden > 0 ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setShowHidden((v) => !v);
            }}
            className="text-meta text-purple-700 hover:underline"
          >
            {showHidden ? "hide dismissed" : `show ${counts.hidden} dismissed`}
          </button>
        ) : null
      }
    >
      <div className="space-y-2">
        {data.kids.map((kid) => {
          const ds = new Set(dismissedByKid[String(kid.child_id)] ?? []);
          const visibleItems = kid.items.filter((it) =>
            showHidden ? true : !ds.has(dismissKey(it)),
          );
          if (visibleItems.length === 0) return null;
          return (
            <div key={kid.child_id}>
              <div className="text-meta font-semibold text-gray-700 mb-1">
                {kid.display_name}
              </div>
              <ul className="space-y-0.5">
                {visibleItems.map((it) => {
                  const k = dismissKey(it);
                  const dismissed = ds.has(k);
                  return (
                    <li
                      key={k}
                      className={
                        trayLineClass("purple") +
                        " flex items-baseline gap-2 flex-wrap " +
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
                        className="h-3.5 w-3.5 accent-blue-700 cursor-pointer self-center"
                      />
                      <span className="text-meta uppercase tracking-wider text-gray-500 shrink-0 w-20 truncate">
                        {it.subject}
                      </span>
                      <span
                        className={
                          "text-gray-900 truncate min-w-0 flex-1 " +
                          (dismissed ? "line-through" : "")
                        }
                      >
                        {it.topic}
                      </span>
                      <span
                        className={
                          "text-meta inline-flex items-center px-1.5 py-0 rounded border " +
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
                            className={`text-meta inline-flex items-center px-1.5 py-0 rounded border ${meta.tone}`}
                          >
                            {meta.label}
                          </span>
                        );
                      })()}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </Tray>
  );
}
