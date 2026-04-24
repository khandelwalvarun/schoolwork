import { useRef } from "react";
import { Assignment } from "../api";
import TitleBlock from "./TitleBlock";
import Attachments from "./Attachments";
import QuickActions from "./QuickActions";
import { EffectiveStatusChip } from "./StatusPopover";

function PriorityStar({ n }: { n: number }) {
  if (n <= 0) return null;
  return <span className="text-amber-500 text-xs mr-1">{"★".repeat(n)}</span>;
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
  return (
    <div
      className={"row cursor-pointer " + (isSelected ? "selected" : "")}
      onClick={() => onOpenAudit(a)}
      role="row"
    >
      <div onClick={(e) => e.stopPropagation()} className="flex items-center justify-center">
        <SelectBox
          id={a.id}
          checked={isSelected}
          onToggle={onToggleSelect}
          ariaLabel={`Select ${a.title ?? "assignment"}`}
        />
      </div>
      <div className="text-gray-600 truncate">
        <PriorityStar n={a.priority} />
        {a.subject}
      </div>
      <div className="min-w-0">
        <TitleBlock title={a.title} titleEn={a.title_en} className="truncate" />
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
      <div className="text-gray-500 text-xs whitespace-nowrap">{a.due_or_date ?? "—"}</div>
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
}: {
  label: string;
  count: number;
  allSelected: boolean;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  tone?: "red" | "amber" | "blue" | "default";
}) {
  const toneClass =
    tone === "red"   ? "text-red-700"
  : tone === "amber" ? "text-amber-700"
  : tone === "blue"  ? "text-blue-700"
  : "text-gray-700";
  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-[color:var(--bg-muted)] border-t border-b border-[color:var(--line-soft)]">
      <input
        type="checkbox"
        checked={allSelected}
        onChange={allSelected ? onDeselectAll : onSelectAll}
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
}) {
  if (!rows.length) return null;
  const allSelected = rows.every((r) => selection.ids.has(r.id));
  return (
    <div>
      <BucketHeader
        label={label}
        count={rows.length}
        allSelected={allSelected}
        onSelectAll={() => selection.selectMany(rows.map((r) => r.id))}
        onDeselectAll={() => selection.deselectMany(rows.map((r) => r.id))}
        tone={tone}
      />
      {rows.map((a) => (
        <AssignmentRow
          key={a.id}
          a={a}
          isSelected={selection.ids.has(a.id)}
          onToggleSelect={selection.toggle}
          onOpenAudit={onOpenAudit}
          onOpenPopover={onOpenPopover}
        />
      ))}
    </div>
  );
}
