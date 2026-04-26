import { useCallback, useEffect, useRef, useState } from "react";

/** Shape of the backend-persisted UI prefs. */
export type UiPrefs = {
  collapsed: Record<string, boolean>;
  bucket_order: Record<string, string[]>;  // childId → ["overdue","due_today","upcoming"]
  kid_order: number[];
  sync_interval_hours?: number;
  sync_window_start_hour?: number;
  sync_window_end_hour?: number;
  /** "horizontal" (default, original wrap-flex top nav) | "sidebar"
   *  (Linear/Notion-style left rail). Phase 9 lever. */
  nav_layout?: "horizontal" | "sidebar";
  /** Dismissed shaky-topic rows: childId → ["subject::topic", …].
   *  Per-item dismiss persists here so the same rows don't keep
   *  reappearing on every page load. */
  shaky_dismissed?: Record<string, string[]>;
};

const DEFAULT: UiPrefs = {
  collapsed: {},
  bucket_order: {},
  kid_order: [],
  sync_interval_hours: 1,
  sync_window_start_hour: 8,
  sync_window_end_hour: 22,
  nav_layout: "horizontal",
  shaky_dismissed: {},
};

/** Client-side wrapper around GET/PUT /api/ui-prefs.
 *
 *   - First render fetches once and hydrates.
 *   - Writes are debounced (150ms) so dragging or mass-toggling doesn't
 *     hammer the server.
 *   - Returns a plain value + a mutation helper; consumers read the pref
 *     and call `update(partial)` to change it. Optimistic — state updates
 *     immediately, PUT follows in the background.
 *   - `isCollapsed(id, defaultCollapsed=true)` — first-time items default
 *     to COLLAPSED unless an explicit `false` has been saved.
 */
export function useUiPrefs() {
  const [prefs, setPrefs] = useState<UiPrefs>(DEFAULT);
  const [loaded, setLoaded] = useState(false);
  const pendingRef = useRef<UiPrefs | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/ui-prefs")
      .then((r) => r.ok ? r.json() : DEFAULT)
      .then((p: UiPrefs) => {
        if (cancelled) return;
        setPrefs({
          collapsed: p.collapsed || {},
          bucket_order: p.bucket_order || {},
          kid_order: p.kid_order || [],
          sync_interval_hours: p.sync_interval_hours ?? 1,
          sync_window_start_hour: p.sync_window_start_hour ?? 8,
          sync_window_end_hour: p.sync_window_end_hour ?? 22,
          nav_layout: p.nav_layout ?? "horizontal",
          shaky_dismissed: p.shaky_dismissed ?? {},
        });
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
    return () => { cancelled = true; };
  }, []);

  const persist = useCallback((next: UiPrefs) => {
    pendingRef.current = next;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      const body = pendingRef.current;
      if (!body) return;
      pendingRef.current = null;
      fetch("/api/ui-prefs", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).catch(() => { /* best-effort */ });
    }, 150);
  }, []);

  const update = useCallback((patch: Partial<UiPrefs>) => {
    setPrefs((prev) => {
      const next: UiPrefs = {
        collapsed:    { ...prev.collapsed,    ...(patch.collapsed    || {}) },
        bucket_order: { ...prev.bucket_order, ...(patch.bucket_order || {}) },
        kid_order: patch.kid_order !== undefined ? patch.kid_order : prev.kid_order,
        sync_interval_hours:    patch.sync_interval_hours    ?? prev.sync_interval_hours,
        sync_window_start_hour: patch.sync_window_start_hour ?? prev.sync_window_start_hour,
        sync_window_end_hour:   patch.sync_window_end_hour   ?? prev.sync_window_end_hour,
        nav_layout: patch.nav_layout ?? prev.nav_layout,
        shaky_dismissed: patch.shaky_dismissed !== undefined
          ? patch.shaky_dismissed
          : prev.shaky_dismissed,
      };
      persist(next);
      return next;
    });
  }, [persist]);

  /** Default to COLLAPSED unless the user has explicitly opened a bucket. */
  const isCollapsed = useCallback((id: string, defaultCollapsed = true) => {
    const saved = prefs.collapsed[id];
    if (saved === undefined) return defaultCollapsed;
    return saved;
  }, [prefs.collapsed]);

  const setCollapsed = useCallback((id: string, v: boolean) => {
    update({ collapsed: { [id]: v } });
  }, [update]);

  const toggleCollapsed = useCallback((id: string, defaultCollapsed = true) => {
    const cur = isCollapsed(id, defaultCollapsed);
    setCollapsed(id, !cur);
  }, [isCollapsed, setCollapsed]);

  const setBucketOrder = useCallback((childId: number, order: string[]) => {
    update({ bucket_order: { [String(childId)]: order } });
  }, [update]);

  const bucketOrderFor = useCallback(
    (childId: number, fallback: string[]): string[] => {
      const stored = prefs.bucket_order[String(childId)];
      if (!stored || stored.length === 0) return fallback;
      // sanity: keep only known buckets, append missing
      const known = new Set(fallback);
      const filtered = stored.filter((b) => known.has(b));
      for (const b of fallback) if (!filtered.includes(b)) filtered.push(b);
      return filtered;
    },
    [prefs.bucket_order],
  );

  const setKidOrder = useCallback((order: number[]) => {
    update({ kid_order: order });
  }, [update]);

  const setShakyDismissed = useCallback(
    (next: Record<string, string[]>) => {
      update({ shaky_dismissed: next });
    },
    [update],
  );

  return {
    prefs,
    loaded,
    isCollapsed,
    setCollapsed,
    toggleCollapsed,
    setBucketOrder,
    bucketOrderFor,
    setKidOrder,
    setShakyDismissed,
  };
}
