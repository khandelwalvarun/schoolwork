/**
 * useItemCommentCounts — bulk-fetch comment counts for a set of item
 * ids. Used by the assignment list to show a 💭N indicator next to
 * rows that have parent observations attached.
 *
 * The API endpoint accepts a comma-joined ids list and returns
 * {"id": count} so we avoid N+1 round-trips. Cached per-id-set in
 * React Query so toggling buckets / re-rendering doesn't refetch.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export function useItemCommentCounts(ids: number[]): Record<number, number> {
  // Stable cache key — sorted ids so the same set in any order
  // dedupes to one query.
  const sortedIds = [...ids].sort((a, b) => a - b);
  const key = sortedIds.join(",");
  const { data } = useQuery({
    queryKey: ["item-comment-counts", key],
    queryFn: () => api.itemCommentCounts(sortedIds),
    enabled: ids.length > 0,
    staleTime: 30_000,
  });
  if (!data) return {};
  // API returns Record<string, number> (JSON keys are strings); map
  // back to number-keyed for caller convenience.
  const out: Record<number, number> = {};
  for (const k of Object.keys(data)) {
    out[Number(k)] = data[k];
  }
  return out;
}
