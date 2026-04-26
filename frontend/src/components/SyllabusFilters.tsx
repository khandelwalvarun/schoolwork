/**
 * Filter strip for the Syllabus page.
 *
 * Three filters, ANDed together:
 *   - language    en / hi / sa (toggle multiple; empty = no filter)
 *   - state       focus on a mastery state (e.g. "decaying only", "unmastered only")
 *   - coverage    "covered only" or "uncovered only"
 *
 * Filters live in URL hash so refresh and link-share preserve them.
 */
import { LanguageCode, MasteryState } from "../api";

type StateFilter = NonNullable<MasteryState> | "unmastered" | null;

export type SyllabusFilterState = {
  langs: Set<NonNullable<LanguageCode>>;
  state: StateFilter;
  coverage: "covered" | "uncovered" | null;
};

export function emptyFilters(): SyllabusFilterState {
  return { langs: new Set(), state: null, coverage: null };
}

const LANG_BTN: Record<NonNullable<LanguageCode>, { label: string; active: string; idle: string }> = {
  en: { label: "EN",      active: "border-blue-400 text-blue-800 bg-blue-100",   idle: "border-blue-200 text-blue-700 bg-blue-50/50" },
  hi: { label: "हिन्दी", active: "border-amber-400 text-amber-800 bg-amber-100", idle: "border-amber-200 text-amber-700 bg-amber-50/50" },
  sa: { label: "संस्कृत", active: "border-purple-400 text-purple-800 bg-purple-100", idle: "border-purple-200 text-purple-700 bg-purple-50/50" },
};

const STATE_BTN: Array<{ key: StateFilter; label: string }> = [
  { key: null,         label: "all"        },
  { key: "decaying",   label: "decaying"   },
  { key: "unmastered", label: "unmastered" },
  { key: "mastered",   label: "mastered"   },
];

export function SyllabusFilters({
  filters,
  onChange,
  topicCount,
  shownCount,
}: {
  filters: SyllabusFilterState;
  onChange: (next: SyllabusFilterState) => void;
  topicCount: number;
  shownCount: number;
}) {
  const toggleLang = (l: NonNullable<LanguageCode>) => {
    const next = new Set(filters.langs);
    if (next.has(l)) next.delete(l);
    else next.add(l);
    onChange({ ...filters, langs: next });
  };
  const setState = (s: StateFilter) => onChange({ ...filters, state: s });
  const reset = () => onChange(emptyFilters());

  const anyActive =
    filters.langs.size > 0 || filters.state !== null || filters.coverage !== null;

  return (
    <div className="flex items-center gap-2 mb-3 text-xs flex-wrap">
      <span className="text-gray-500 mr-1">Filter:</span>

      {(Object.keys(LANG_BTN) as Array<NonNullable<LanguageCode>>).map((l) => {
        const meta = LANG_BTN[l];
        const active = filters.langs.has(l);
        return (
          <button
            key={l}
            type="button"
            onClick={() => toggleLang(l)}
            className={`px-2 py-0.5 rounded border ${
              active ? meta.active : meta.idle
            }`}
            aria-pressed={active}
          >
            {meta.label}
          </button>
        );
      })}

      <span className="text-gray-300 mx-1">|</span>

      {STATE_BTN.map((s) => {
        const active = filters.state === s.key;
        return (
          <button
            key={s.label}
            type="button"
            onClick={() => setState(s.key)}
            className={`px-2 py-0.5 rounded border ${
              active
                ? "border-gray-700 text-gray-900 bg-gray-100"
                : "border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
            aria-pressed={active}
          >
            {s.label}
          </button>
        );
      })}

      <span className="ml-auto text-gray-400">
        {anyActive ? (
          <>
            showing {shownCount} of {topicCount}
            <button
              type="button"
              onClick={reset}
              className="ml-2 text-blue-700 hover:underline"
            >
              clear
            </button>
          </>
        ) : (
          <>{topicCount} topics</>
        )}
      </span>
    </div>
  );
}

/** Helper used by every tab to apply the filter set to a topic list. */
export function filterTopic(
  filters: SyllabusFilterState,
  langOf: (subject: string) => NonNullable<LanguageCode> | null,
  subject: string,
  state: MasteryState,
  coverage: "covered" | "in_progress" | "delayed" | "skipped" | null,
): boolean {
  if (filters.langs.size > 0) {
    const lc = langOf(subject);
    if (!lc || !filters.langs.has(lc)) return false;
  }
  if (filters.state !== null) {
    if (filters.state === "unmastered") {
      if (state === "mastered") return false;
    } else {
      if (state !== filters.state) return false;
    }
  }
  if (filters.coverage === "covered") {
    if (coverage !== "covered") return false;
  }
  if (filters.coverage === "uncovered") {
    if (coverage === "covered") return false;
  }
  return true;
}

/** Mirror of backend services/language.py — keep in lockstep. */
export function langOf(subject: string | null | undefined): NonNullable<LanguageCode> | null {
  if (!subject) return null;
  const s = subject.toLowerCase();
  if (s.includes("sanskrit")) return "sa";
  if (s.includes("hindi")) return "hi";
  if (s.includes("english")) return "en";
  return null;
}
