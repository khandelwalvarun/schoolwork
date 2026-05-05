import { useRef, useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Assignment, ParentStatus } from "../api";
import TitleBlock from "./TitleBlock";
import Attachments from "./Attachments";
import QuickActions from "./QuickActions";
import { ReviewPracticeButton } from "./ReviewPracticeButton";
import { EffectiveStatusChip } from "./StatusPopover";
import { CategoryChip, WorthAChatChip } from "./StatusChips";
import { useOptimisticPatch } from "./useOptimisticPatch";
import { useItemCommentCounts } from "./useItemCommentCounts";
import { formatDate } from "../util/dates";

function PriorityStar({ n }: { n: number }) {
  if (n <= 0) return null;
  // Single star, opacity-graded by priority. Three stacked stars
  // visually screamed even when nothing was overdue. One star, darker
  // = higher priority, reads as a pellet rather than a row of asterisks.
  const tone =
    n >= 3 ? "text-amber-600" : n === 2 ? "text-amber-500" : "text-amber-400";
  return (
    <span
      className={`${tone} text-xs mr-1`}
      title={`Priority ${n}`}
      aria-label={`Priority ${n}`}
    >
      ★
    </span>
  );
}

/** Category leading badge — solid H/R/C letter so the left edge of
 *  the list reads as a colour-coded skim. Canonical implementation
 *  lives in StatusChips.tsx (CategoryChip); we wrap it here to keep
 *  the row's `mr-2` spacing without polluting the canonical chip. */
function CategoryBadge({ category }: { category: string | null | undefined }) {
  return (
    <span className="mr-2 inline-flex">
      <CategoryChip category={category as "homework" | "review" | "classwork" | null | undefined} />
    </span>
  );
}

function SelectBox({
  id,
  checked,
  onToggle,
  ariaLabel,
}: {
  id: number;
  checked: boolean;
  onToggle: (id: number) => void;
  ariaLabel: string;
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={() => onToggle(id)}
      onClick={(e) => e.stopPropagation()}
      aria-label={ariaLabel}
      className="h-4 w-4 accent-blue-700 cursor-pointer"
    />
  );
}

function StatusChipButton({
  a,
  onOpenPopover,
}: {
  a: Assignment;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
}) {
  const ref = useRef<HTMLButtonElement | null>(null);
  return (
    <button
      ref={ref}
      onClick={(e) => {
        e.stopPropagation();
        onOpenPopover(a, (ref.current as HTMLButtonElement).getBoundingClientRect());
      }}
      title="Click to update status"
      className="cursor-pointer"
    >
      <EffectiveStatusChip a={a} />
    </button>
  );
}

export function AssignmentRow({
  a,
  isSelected,
  onToggleSelect,
  onOpenAudit,
  onOpenPopover,
  commentCount = 0,
}: {
  a: Assignment;
  isSelected: boolean;
  onToggleSelect: (id: number) => void;
  onOpenAudit: (a: Assignment) => void;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
  commentCount?: number;
}) {
  // Phase 24 — attention zone styles. Fresh: amber left-rule + soft tint.
  // Archived: muted text + line-through title. Steady: default.
  const zone = a.attention_zone || "steady";
  // Calmer zone styling — narrower fresh accent rule, softer tint.
  // The previous border-l-4 + bg-amber-50/30 read as a warning band
  // even though "fresh" is just informational.
  const zoneClass =
    zone === "fresh"
      ? " border-l-2 border-l-amber-300"
      : zone === "archived"
      ? " text-gray-400"
      : "";
  const optimisticPatch = useOptimisticPatch();
  // Keyboard quick-mark: pressing "d" while the row is focused
  // toggles done-at-home. "p" toggles worth-a-chat. "s" snoozes 1
  // day. Single-key shortcuts only fire when the row itself has
  // focus (not when typing in a child input), so they don't trip
  // unexpectedly. See QuickActions for the same actions on click.
  const onRowKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "d") {
      e.preventDefault();
      const isDone =
        a.parent_status === "done_at_home" || a.parent_status === "submitted";
      const next: ParentStatus | null =
        isDone && a.parent_status === "done_at_home" ? null : "done_at_home";
      optimisticPatch(a.id, { parent_status: next }, {
        label: next ? "Marked done at home" : "Marked not done",
      });
    } else if (e.key === "p") {
      e.preventDefault();
      optimisticPatch(a.id, { discuss_with_teacher: !a.discuss_with_teacher_at }, {
        label: a.discuss_with_teacher_at
          ? "Cleared 'worth a chat'"
          : "Flagged for PTM chat",
      });
    } else if (e.key === "Enter") {
      e.preventDefault();
      onOpenAudit(a);
    }
  };
  return (
    <div
      className={
        "row cursor-pointer focus:bg-[color:var(--accent-bg)] focus:outline-none " +
        (isSelected ? "selected " : "") +
        zoneClass
      }
      onClick={() => onOpenAudit(a)}
      onKeyDown={onRowKey}
      role="row"
      tabIndex={0}
      aria-label={`${a.subject ?? ""}: ${a.title ?? "assignment"}. Press d to mark done, p to flag for PTM chat, Enter to open.`}
    >
      <div onClick={(e) => e.stopPropagation()} className="flex items-center justify-center">
        <SelectBox
          id={a.id}
          checked={isSelected}
          onToggle={onToggleSelect}
          ariaLabel={`Select ${a.title ?? "assignment"}`}
        />
      </div>
      <div className={"truncate flex items-center " + (zone === "archived" ? "text-gray-400" : "text-gray-600")}>
        <CategoryBadge category={a.work_category ?? null} />
        <PriorityStar n={a.priority} />
        <span className="truncate">{a.subject}</span>
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <TitleBlock
            title={a.title}
            titleEn={a.title_en}
            className={"truncate " + (zone === "archived" ? "line-through decoration-gray-300" : "")}
          />
          {zone === "fresh" && (
            <span
              className="shrink-0 text-[10px] text-amber-700"
              title="New within the last 48 hours"
            >
              · new
            </span>
          )}
          {a.discuss_with_teacher_at && (
            <WorthAChatChip note={a.discuss_with_teacher_note} compact />
          )}
          {commentCount > 0 && (
            // Comment indicator — bumped to text-meta + chip-gray so
            // it reads at the same weight as the worth-a-chat chip
            // sibling. Previously two distinct micro-sizes
            // (text-[11px] + text-[10px] inside) made it visually
            // muddy.
            <span
              className="chip-gray text-meta inline-flex items-center gap-0.5"
              title={`${commentCount} parent comment${commentCount === 1 ? "" : "s"} on this item — open the audit drawer to read them`}
            >
              💭 <span className="font-semibold">{commentCount}</span>
            </span>
          )}
          <ReviewPracticeButton a={a} />
        </div>
        {(a.syllabus_context || (a.attachments && a.attachments.length > 0) || a.tags.length > 0) && (
          <div className="text-xs mt-0.5 space-y-0.5">
            {a.syllabus_context && (
              <div className="text-gray-500">↳ {a.syllabus_context}</div>
            )}
            {a.attachments && a.attachments.length > 0 && (
              <Attachments items={a.attachments} />
            )}
            {a.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {a.tags.map((t) => (
                  <span key={t} className="chip-gray">{t}</span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <div className="text-gray-500 text-xs whitespace-nowrap" title={a.due_or_date ?? ""}>
        {formatDate(a.due_or_date)}
      </div>
      <div className="flex items-center gap-2 justify-end" onClick={(e) => e.stopPropagation()}>
        <StatusChipButton a={a} onOpenPopover={onOpenPopover} />
        <div className="hover-reveal">
          <QuickActions a={a} />
        </div>
      </div>
    </div>
  );
}

export function BucketHeader({
  label,
  count,
  allSelected,
  onSelectAll,
  onDeselectAll,
  tone = "default",
  collapsed,
  onToggleCollapsed,
  dragHandle,
}: {
  label: string;
  count: number;
  allSelected: boolean;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  tone?: "red" | "amber" | "blue" | "default";
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  dragHandle?: React.ReactNode;
}) {
  const toneClass =
    tone === "red"   ? "text-red-700"
  : tone === "amber" ? "text-amber-700"
  : tone === "blue"  ? "text-blue-700"
  : "text-gray-700";
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onToggleCollapsed}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggleCollapsed?.();
        }
      }}
      // Slimmer bucket header — gap-2 instead of gap-3, py-1.5
      // instead of py-2, smaller chevron + checkbox. Sits closer in
      // weight to the Tray strip headers above so the eye reads them
      // as the same family. The drag handle (when present) reveals
      // only on group-hover so the steady state is calm.
      className="w-full group flex items-center gap-2 px-3 py-1.5 bg-[color:var(--bg-muted)] border-t border-b border-[color:var(--line-soft)] hover:bg-[color:var(--bg-sunken)] transition-colors text-left cursor-pointer select-none"
      aria-expanded={!collapsed}
      title={collapsed ? "Expand" : "Collapse"}
    >
      {dragHandle && (
        <span className="opacity-0 group-hover:opacity-100 transition-opacity">
          {dragHandle}
        </span>
      )}
      <span
        className={"inline-block text-gray-400 transition-transform " + (collapsed ? "" : "rotate-90")}
        style={{ width: 8 }}
        aria-hidden
      >
        ▶
      </span>
      <input
        type="checkbox"
        checked={allSelected}
        onChange={allSelected ? onDeselectAll : onSelectAll}
        onClick={(e) => e.stopPropagation()}
        aria-label={allSelected ? "Deselect all" : "Select all"}
        className="h-3.5 w-3.5 accent-blue-700 cursor-pointer"
      />
      <h4 className={"h-section " + toneClass}>
        {label} · {count}
      </h4>
    </div>
  );
}

export function AssignmentList({
  rows,
  label,
  tone,
  selection,
  onOpenAudit,
  onOpenPopover,
  bucketId,
  collapsed,
  onToggleCollapsed,
  sortableId,
  flatRender = false,
}: {
  rows: Assignment[];
  label: string;
  tone?: "red" | "amber" | "blue" | "default";
  selection: {
    ids: Set<number>;
    toggle: (id: number) => void;
    selectMany: (ids: Iterable<number>) => void;
    deselectMany: (ids: Iterable<number>) => void;
  };
  onOpenAudit: (a: Assignment) => void;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
  bucketId?: string;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  sortableId?: string;
  /** When true, render rows in the order given (no FRESH/STEADY/
   *  ARCHIVED partition). Used by the sortable Assignments page so
   *  the user's chosen sort isn't fragmented by attention zones. */
  flatRender?: boolean;
}) {
  if (!rows.length) return null;
  const allSelected = rows.every((r) => selection.ids.has(r.id));

  // Optional drag support — when `sortableId` provided, the bucket can be
  // reordered inside a parent SortableContext.
  const sortable = useSortable({ id: sortableId || `__noop__${bucketId || label}` });
  const dragProps = sortableId
    ? {
        ref: sortable.setNodeRef,
        style: {
          transform: CSS.Transform.toString(sortable.transform),
          transition: sortable.transition,
          opacity: sortable.isDragging ? 0.5 : 1,
        } as React.CSSProperties,
      }
    : {};
  const dragHandle = sortableId ? (
    <span
      {...sortable.attributes}
      {...sortable.listeners}
      className="text-gray-300 hover:text-gray-600 cursor-grab active:cursor-grabbing select-none"
      style={{ width: 12 }}
      onClick={(e) => e.stopPropagation()}
      title="Drag to reorder"
      aria-label="Drag handle"
    >
      ⋮⋮
    </span>
  ) : null;

  return (
    <div {...dragProps}>
      <BucketHeader
        label={label}
        count={rows.length}
        allSelected={allSelected}
        onSelectAll={() => selection.selectMany(rows.map((r) => r.id))}
        onDeselectAll={() => selection.deselectMany(rows.map((r) => r.id))}
        tone={tone}
        collapsed={collapsed}
        onToggleCollapsed={onToggleCollapsed}
        dragHandle={dragHandle}
      />
      {!collapsed && (
        flatRender ? (
          <FlatRows
            rows={rows}
            selection={selection}
            onOpenAudit={onOpenAudit}
            onOpenPopover={onOpenPopover}
          />
        ) : (
          <ZoneSplitRows
            rows={rows}
            selection={selection}
            onOpenAudit={onOpenAudit}
            onOpenPopover={onOpenPopover}
          />
        )
      )}
    </div>
  );
}

/** Flat render — used by sortable views (e.g. /child/:id/assignments)
 *  where the parent has already ordered the rows and we shouldn't
 *  fragment that order with FRESH/STEADY/ARCHIVED partitioning. */
function FlatRows({
  rows,
  selection,
  onOpenAudit,
  onOpenPopover,
}: {
  rows: Assignment[];
  selection: {
    ids: Set<number>;
    toggle: (id: number) => void;
    selectMany: (ids: Iterable<number>) => void;
    deselectMany: (ids: Iterable<number>) => void;
  };
  onOpenAudit: (a: Assignment) => void;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
}) {
  const counts = useItemCommentCounts(rows.map((r) => r.id));
  return (
    <>
      {rows.map((a) => (
        <AssignmentRow
          key={a.id}
          a={a}
          isSelected={selection.ids.has(a.id)}
          onToggleSelect={selection.toggle}
          onOpenAudit={onOpenAudit}
          onOpenPopover={onOpenPopover}
          commentCount={counts[a.id] || 0}
        />
      ))}
    </>
  );
}

/** Phase 24: Partition rows by attention_zone and render in
 *   FRESH → STEADY → ARCHIVED order. ARCHIVED items collapse behind a
 *   "Done · N" toggle so the eye doesn't have to scan past completed
 *   work to find what still needs attention. The split is invisible
 *   when every row is in the same zone (e.g. all-fresh, or all-steady
 *   on a quiet day). */
function ZoneSplitRows({
  rows,
  selection,
  onOpenAudit,
  onOpenPopover,
}: {
  rows: Assignment[];
  selection: {
    ids: Set<number>;
    toggle: (id: number) => void;
    selectMany: (ids: Iterable<number>) => void;
    deselectMany: (ids: Iterable<number>) => void;
  };
  onOpenAudit: (a: Assignment) => void;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
}) {
  const fresh = rows.filter((r) => r.attention_zone === "fresh");
  const archived = rows.filter((r) => r.attention_zone === "archived");
  const steady = rows.filter(
    (r) => r.attention_zone !== "fresh" && r.attention_zone !== "archived",
  );
  const [archiveOpen, setArchiveOpen] = useState(false);

  // One bulk fetch for all rows in this bucket — much cheaper than
  // per-row queries. The hook keys on the sorted id set so the cache
  // dedupes across rerenders.
  const counts = useItemCommentCounts(rows.map((r) => r.id));

  const renderRow = (a: Assignment) => (
    <AssignmentRow
      key={a.id}
      a={a}
      isSelected={selection.ids.has(a.id)}
      onToggleSelect={selection.toggle}
      onOpenAudit={onOpenAudit}
      onOpenPopover={onOpenPopover}
      commentCount={counts[a.id] || 0}
    />
  );

  return (
    <>
      {fresh.length > 0 && fresh.map(renderRow)}
      {steady.length > 0 && steady.map(renderRow)}
      {archived.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setArchiveOpen((v) => !v)}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-500 bg-[color:var(--bg-app)] hover:bg-[color:var(--bg-muted)] border-t border-[color:var(--line-soft)] text-left"
            aria-expanded={archiveOpen}
          >
            <span
              className={
                "inline-block text-gray-400 transition-transform " +
                (archiveOpen ? "rotate-90" : "")
              }
              style={{ width: 8 }}
              aria-hidden
            >
              ▶
            </span>
            <span>Done</span>
            <span className="font-semibold text-gray-600">· {archived.length}</span>
            <span className="ml-auto text-[11px] text-gray-400">
              auto-hidden after 24h
            </span>
          </button>
          {archiveOpen && archived.map(renderRow)}
        </>
      )}
    </>
  );
}
