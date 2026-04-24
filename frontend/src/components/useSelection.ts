import { useCallback, useMemo, useState } from "react";

/** Generic multi-select hook — tracks a Set<number> and exposes helpers. */
export function useSelection() {
  const [ids, setIds] = useState<Set<number>>(new Set());

  const toggle = useCallback((id: number) => {
    setIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const set = useCallback((id: number, on: boolean) => {
    setIds((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const clear = useCallback(() => setIds(new Set()), []);

  const selectMany = useCallback((ids_: Iterable<number>) => {
    setIds((prev) => {
      const next = new Set(prev);
      for (const id of ids_) next.add(id);
      return next;
    });
  }, []);

  const deselectMany = useCallback((ids_: Iterable<number>) => {
    setIds((prev) => {
      const next = new Set(prev);
      for (const id of ids_) next.delete(id);
      return next;
    });
  }, []);

  const list = useMemo(() => Array.from(ids), [ids]);

  return { ids, list, toggle, set, clear, selectMany, deselectMany };
}
