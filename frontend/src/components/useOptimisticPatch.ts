/**
 * useOptimisticPatch — wraps `api.patchAssignment` so the UI flips
 * immediately and the network catches up afterwards.
 *
 * Pattern (TanStack Query optimistic updates):
 *   1. onMutate: snapshot every cached query that contains the assignment,
 *      apply the patch in-place, return the snapshot
 *   2. onError: restore from snapshot + show error toast
 *   3. onSuccess: show "X • Undo (Z)" toast that, when triggered, sends a
 *      reverse PATCH and restores caches
 *
 * Reverse-patch logic is per-field:
 *   - parent_status: previous value
 *   - priority:      previous integer (or 0 if unset)
 *   - snooze_until:  previous string or null
 *   - status_notes:  previous string or null
 *   - tags:          previous array (deep-copied)
 *
 * Caches walked: every active query whose data is an Assignment[] or contains
 * Assignment[] arrays (Today, ChildDetail, ChildBoard, ChildAssignments,
 * Overdue/DueToday/Upcoming). The walker visits known shapes; unknown shapes
 * are skipped silently — they'll just re-fetch on invalidate.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Assignment, AssignmentPatch, api } from "../api";
import { useToast } from "./Toast";

type CacheSnapshot = { queryKey: readonly unknown[]; data: unknown }[];

function applyPatchToRow(
  row: Record<string, unknown>,
  patch: AssignmentPatch,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...row, ...patch };
  // The patch wire-format is `{ discuss_with_teacher: bool }` but the
  // cached row exposes `discuss_with_teacher_at` (timestamp). Translate
  // so the optimistic update flips the visible state correctly.
  if ("discuss_with_teacher" in patch) {
    next.discuss_with_teacher_at = patch.discuss_with_teacher
      ? (row.discuss_with_teacher_at ?? new Date().toISOString())
      : null;
    if (!patch.discuss_with_teacher) {
      next.discuss_with_teacher_note = null;
    }
    delete (next as Record<string, unknown>).discuss_with_teacher;
  }
  return next;
}

function walkAndPatch(
  data: unknown,
  itemId: number,
  patch: AssignmentPatch,
): unknown {
  if (Array.isArray(data)) {
    return data.map((x) => walkAndPatch(x, itemId, patch));
  }
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    // Direct match: a bare Assignment row
    if (typeof obj.id === "number" && obj.id === itemId && "parent_status" in obj) {
      return applyPatchToRow(obj, patch);
    }
    // Object containing Assignment arrays — walk into each value
    const out: Record<string, unknown> = { ...obj };
    let changed = false;
    for (const k of Object.keys(out)) {
      const next = walkAndPatch(out[k], itemId, patch);
      if (next !== out[k]) {
        out[k] = next;
        changed = true;
      }
    }
    return changed ? out : data;
  }
  return data;
}

function snapshotPrev(item: Assignment, patch: AssignmentPatch): AssignmentPatch {
  const reverse: AssignmentPatch = {};
  if ("parent_status" in patch) reverse.parent_status = item.parent_status ?? null;
  if ("priority" in patch) reverse.priority = item.priority ?? 0;
  if ("snooze_until" in patch) reverse.snooze_until = item.snooze_until ?? null;
  if ("status_notes" in patch) reverse.status_notes = item.status_notes ?? null;
  if ("tags" in patch) reverse.tags = [...(item.tags ?? [])];
  if ("discuss_with_teacher" in patch) {
    reverse.discuss_with_teacher = !!item.discuss_with_teacher_at;
  }
  if ("discuss_with_teacher_note" in patch) {
    reverse.discuss_with_teacher_note = item.discuss_with_teacher_note ?? null;
  }
  return reverse;
}

function findAssignmentInCache(qc: ReturnType<typeof useQueryClient>, itemId: number): Assignment | null {
  let found: Assignment | null = null;
  qc.getQueryCache().getAll().forEach((q) => {
    if (found) return;
    const visit = (d: unknown): void => {
      if (found) return;
      if (Array.isArray(d)) { d.forEach(visit); return; }
      if (d && typeof d === "object") {
        const o = d as Record<string, unknown>;
        if (typeof o.id === "number" && o.id === itemId && "parent_status" in o) {
          found = o as unknown as Assignment;
          return;
        }
        Object.values(o).forEach(visit);
      }
    };
    visit(q.state.data);
  });
  return found;
}

export type OptimisticPatch = (
  itemId: number,
  patch: AssignmentPatch,
  opts?: {
    /** Toast message on success. Default: "Updated". */
    label?: string;
    /** If false, no toast is shown. Default: true. */
    showToast?: boolean;
    /** If false, no Undo affordance on the toast. Default: true. */
    undoable?: boolean;
  },
) => Promise<void>;

/** Hook — returns a function the caller invokes with (itemId, patch). */
export function useOptimisticPatch(): OptimisticPatch {
  const qc = useQueryClient();
  const toast = useToast();

  return async (itemId, patch, opts = {}) => {
    const label = opts.label ?? "Updated";
    const showToast = opts.showToast ?? true;
    const undoable = opts.undoable ?? true;

    // Capture prior assignment + cache state for rollback.
    const prev = findAssignmentInCache(qc, itemId);
    const reverse = prev ? snapshotPrev(prev, patch) : null;
    const snapshot: CacheSnapshot = [];
    qc.getQueryCache().getAll().forEach((q) => {
      snapshot.push({ queryKey: q.queryKey, data: q.state.data });
    });

    // Apply optimistic update across every active query.
    qc.getQueryCache().getAll().forEach((q) => {
      const next = walkAndPatch(q.state.data, itemId, patch);
      if (next !== q.state.data) {
        qc.setQueryData(q.queryKey, next);
      }
    });

    try {
      await api.patchAssignment(itemId, patch);
    } catch (e) {
      // Roll back the cache, then bubble.
      snapshot.forEach((s) => qc.setQueryData(s.queryKey, s.data));
      toast.show({ message: `Failed: ${String(e)}`, tone: "error" });
      throw e;
    }

    // Settle: invalidate the most-likely-stale queries so server-side derived
    // fields (effective_status, audit log) refresh in the background.
    qc.invalidateQueries({ queryKey: ["today"] });
    qc.invalidateQueries({ queryKey: ["assignments-board"] });
    qc.invalidateQueries({ queryKey: ["history", itemId] });

    if (showToast) {
      toast.show({
        message: label,
        tone: "success",
        onUndo: undoable && reverse ? async () => {
          // Apply the reverse optimistically, then PATCH it.
          qc.getQueryCache().getAll().forEach((q) => {
            const next = walkAndPatch(q.state.data, itemId, reverse);
            if (next !== q.state.data) qc.setQueryData(q.queryKey, next);
          });
          try {
            await api.patchAssignment(itemId, { ...reverse, note: "undo" });
            qc.invalidateQueries({ queryKey: ["today"] });
            qc.invalidateQueries({ queryKey: ["assignments-board"] });
            qc.invalidateQueries({ queryKey: ["history", itemId] });
            toast.show({ message: "Reverted", tone: "info", ttlMs: 1500 });
          } catch (e) {
            // Roll forward — if the server rejected the undo, force-refresh.
            qc.invalidateQueries({ queryKey: ["today"] });
            qc.invalidateQueries({ queryKey: ["assignments-board"] });
            toast.show({ message: `Undo failed: ${String(e)}`, tone: "error" });
          }
        } : undefined,
      });
    }
  };
}
