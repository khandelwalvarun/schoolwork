import { useRef, useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Assignment } from "../api";
import TitleBlock from "./TitleBlock";
import Attachments from "./Attachments";
import QuickActions from "./QuickActions";
import { ReviewPracticeButton } from "./ReviewPracticeButton";
import { EffectiveStatusChip } from "./StatusPopover";
import { formatDate } from "../util/dates";

function PriorityStar({ n }: { n: number }) {
  if (n <= 0) return null;
  return <span className="text-amber-500 text-xs mr-1">{"★".repeat(n)}</span>;
}

/** Phase 26 — solid colour-coded leading badge in the subject
 *  column on EVERY row, sourced from Veracross's own `type` field
 *  (mapped server-side). The intent: scan the left edge of the list
 *  and see at a glance which rows are homework / review / classwork
 *  without reading any text. Three colours, each with a one-letter
 *  monogram so the badge stays readable when squeezed.
 */
function CategoryBadge({ category }: { category: string | null | undefined }) {
  const cat = category || "homework";
  const meta =
    cat === "review"   ? { letter: "R", bg: "bg-purple-600", label: "Review" }
  : cat === "classwork"? { letter: "C", bg: "bg-gray-500",   label: "Classwork (in class)" }
  :                       { letter: "H", bg: "bg-blue-600",  label: "Homework" };
  return (
    <span
      className={
        "shrink-0 inline-flex items-center justify-center w-5 h-5 rounded text-white text-[10px] font-bold mr-2 " +
        meta.bg
      }
      title={meta.label}
      aria-label={meta.label}
    >
      {meta.letter}
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
}: {
  a: Assignment;
  isSelected: boolean;
  onToggleSelect: (id: number) => void;
  onOpenAudit: (a: Assignment) => void;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
}) {
  // Phase 24 — attention zone styles. Fresh: amber left-rule + soft tint.
  // Archived: muted text + line-through title. Steady: default.
  const zone = a.attention_zone || "steady";
  const zoneClass =
    zone === "fresh"
      ? " border-l-4 border-l-amber-300 bg-amber-50/30"
      : zone === "archived"
      ? " text-gray-400"
      : "";
  return (
    <div
      className={
        "row cursor-pointer focus:bg-[color:var(--accent-bg)] focus:outline-none " +
        (isSelected ? "selected " : "") +
        zoneClass
      }
      onClick={() => onOpenAudit(a)}
      role="row"
      tabIndex={0}
      aria-label={`${a.subject ?? ""}: ${a.title ?? "assignment"}`}
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
              className="shrink-0 text-[10px] font-medium text-amber-700 uppercase tracking-wider"
              title="New within the last 48 hours"
            >
              new
            </span>
          )}
          {a.discuss_with_teacher_at && (
            <span
              className="shrink-0 inline-flex items-center gap-0.5 text-[11px] px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-800 border border-violet-200"
              title={
                a.discuss_with_teacher_note
                  ? `Worth a chat at PTM — ${a.discuss_with_teacher_note}`
                  : "Worth a chat at PTM"
              }
            >
              💬 PTM
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
      className="w-full flex items-center gap-3 px-3 py-2 bg-[color:var(--bg-muted)] border-t border-b border-[color:var(--line-soft)] hover:bg-[color:var(--bg-sunken)] transition-colors text-left cursor-pointer select-none"
      aria-expanded={!collapsed}
      title={collapsed ? "Expand" : "Collapse"}
    >
      {dragHandle}
      <span
        className={"inline-block text-gray-400 transition-transform " + (collapsed ? "" : "rotate-90")}
        style={{ width: 10 }}
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
        className="h-4 w-4 accent-blue-700 cursor-pointer"
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
        <ZoneSplitRows
          rows={rows}
          selection={selection}
          onOpenAudit={onOpenAudit}
          onOpenPopover={onOpenPopover}
        />
      )}
    </div>
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

  const renderRow = (a: Assignment) => (
    <AssignmentRow
      key={a.id}
      a={a}
      isSelected={selection.ids.has(a.id)}
      onToggleSelect={selection.toggle}
      onOpenAudit={onOpenAudit}
      onOpenPopover={onOpenPopover}
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
