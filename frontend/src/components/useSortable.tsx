import { useMemo, useState } from "react";

/** Generic sort-by-column hook.
 *
 *   const { sorted, sortKey, sortDir, onHeaderClick, headerProps } =
 *     useSortable(rows, "date", "desc");
 *
 * `keyOf` maps a column id to the raw value used for comparison. Strings
 * compare case-insensitive, numbers naturally, null/undefined sort last.
 * Clicking the active column flips direction; clicking a different column
 * switches to it ascending.
 */
export type SortDir = "asc" | "desc";

export function useSortable<T>(
  rows: T[],
  initialKey: string | null = null,
  initialDir: SortDir = "asc",
  keyOf: (row: T, key: string) => unknown = (row, key) => (row as Record<string, unknown>)[key],
) {
  const [sortKey, setSortKey] = useState<string | null>(initialKey);
  const [sortDir, setSortDir] = useState<SortDir>(initialDir);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const mult = sortDir === "asc" ? 1 : -1;
    const out = [...rows];
    out.sort((a, b) => {
      const va = keyOf(a, sortKey);
      const vb = keyOf(b, sortKey);
      const aNull = va === null || va === undefined || va === "";
      const bNull = vb === null || vb === undefined || vb === "";
      if (aNull && bNull) return 0;
      if (aNull) return 1;   // nulls always last
      if (bNull) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * mult;
      return String(va).toLowerCase().localeCompare(String(vb).toLowerCase()) * mult;
    });
    return out;
  }, [rows, sortKey, sortDir, keyOf]);

  const onHeaderClick = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const indicator = (key: string): string => {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  };

  return { sorted, sortKey, sortDir, onHeaderClick, indicator };
}

/** Render a sortable <th>. Usage:
 *   <SortableTH label="Date" k="date" s={sort} />
 * where `sort` is the return value of useSortable. */
export function SortableTH({
  label,
  k,
  s,
  className = "",
  align = "left",
}: {
  label: string;
  k: string;
  s: { sortKey: string | null; indicator: (k: string) => string; onHeaderClick: (k: string) => void };
  className?: string;
  align?: "left" | "right" | "center";
}) {
  const active = s.sortKey === k;
  const alignCls =
    align === "right"  ? "text-right"
  : align === "center" ? "text-center"
  :                      "text-left";
  return (
    <th
      scope="col"
      onClick={() => s.onHeaderClick(k)}
      className={
        "py-1 px-2 font-medium cursor-pointer select-none hover:bg-gray-100 " +
        alignCls + " " +
        (active ? "text-gray-900" : "text-gray-500") + " " + className
      }
      aria-sort={active ? (s.indicator(k).trim() === "↑" ? "ascending" : "descending") : "none"}
    >
      {label}
      <span className="text-gray-400">{s.indicator(k)}</span>
    </th>
  );
}
