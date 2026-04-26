/**
 * Tabs — accessible tab strip with consistent styling.
 *
 * Pattern: a thin row of buttons separated by a bottom border. Active tab
 * gets a 2 px purple underline + bold label. Inactive tabs are gray and
 * bump to dark on hover.
 *
 * Each tab is a real <button role="tab"> with aria-selected, so keyboard
 * navigation + screen readers work out of the box.
 *
 * Optional `count` chip after the label (e.g. "Resources · 133").
 *
 * Replaces hand-rolled "border-b-2 -mb-px" tab bars in Resources, SpellBee,
 * ChildHeader, and (Phase 9) the future sidebar.
 */
import { ReactNode } from "react";

export type TabItem<TKey extends string | number = string> = {
  key: TKey;
  label: ReactNode;
  count?: number | null;
  /** Optional accessible name override (defaults to label text). */
  ariaLabel?: string;
};

export function Tabs<TKey extends string | number>({
  items,
  active,
  onChange,
  className = "",
  tone = "blue",
}: {
  items: TabItem<TKey>[];
  active: TKey;
  onChange: (key: TKey) => void;
  className?: string;
  tone?: "blue" | "purple" | "amber";
}) {
  const accent =
    tone === "purple" ? "border-purple-500 text-purple-700"
  : tone === "amber"  ? "border-amber-500 text-amber-700"
                      : "border-blue-700 text-blue-700";

  return (
    <div role="tablist" className={`flex gap-1 mb-4 border-b border-[color:var(--line)] ${className}`.trim()}>
      {items.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={String(t.key)}
            role="tab"
            aria-selected={isActive}
            aria-label={t.ariaLabel}
            onClick={() => onChange(t.key)}
            className={
              "px-3 py-2 text-sm border-b-2 -mb-px transition-colors inline-flex items-center gap-1.5 " +
              (isActive
                ? `${accent} font-semibold`
                : "border-transparent text-gray-600 hover:text-gray-900")
            }
          >
            <span>{t.label}</span>
            {typeof t.count === "number" && (
              <span className="text-xs text-gray-500 font-normal">· {t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
