import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import ChildHeader from "../components/ChildHeader";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { api, Assignment, ParentStatus } from "../api";
import StatusPopover, { EffectiveStatusChip } from "../components/StatusPopover";
import AuditDrawer from "../components/AuditDrawer";
import QuickActions from "../components/QuickActions";
import { SkeletonBoardColumn } from "../components/Skeleton";
import { useOptimisticPatch } from "../components/useOptimisticPatch";
import { ReviewPracticeButton } from "../components/ReviewPracticeButton";
import { WorthAChatTray } from "../components/WorthAChatTray";
import { CategoryChip, WorthAChatChip } from "../components/StatusChips";
import { formatDate } from "../util/dates";

type ColumnKey = "not_started" | "in_progress" | "done_at_home" | "submitted" | "graded";

const COLUMN_DEFS: { key: ColumnKey; label: string; accent: string }[] = [
  { key: "not_started",  label: "Not started",  accent: "bg-gray-50 border-gray-200" },
  { key: "in_progress",  label: "In progress",  accent: "bg-amber-50 border-amber-200" },
  { key: "done_at_home", label: "Done at home", accent: "bg-emerald-50 border-emerald-200" },
  { key: "submitted",    label: "Handed in",    accent: "bg-blue-50 border-blue-200" },
  { key: "graded",       label: "Graded",       accent: "bg-purple-50 border-purple-200" },
];

function columnFor(a: Assignment): ColumnKey {
  const eff = a.effective_status;
  if (eff === "graded") return "graded";
  if (eff === "submitted") return "submitted";
  if (eff === "done_at_home") return "done_at_home";
  if (eff === "in_progress") return "in_progress";
  // needs_help, blocked, skipped, overdue, pending — treat as "not started"
  return "not_started";
}

// Map column → the parent_status we set when dropping there.
// (null means "not tracked" → chip falls back to portal status)
const COLUMN_TO_PARENT_STATUS: Record<ColumnKey, ParentStatus | null | "GRADED_NOOP"> = {
  not_started: null,
  in_progress: "in_progress",
  done_at_home: "done_at_home",
  submitted: "submitted",
  graded: "GRADED_NOOP",  // graded is portal-owned; we don't let parent set this
};

function PriorityStar({ n }: { n: number }) {
  if (n <= 0) return null;
  return <span className="text-amber-500 text-xs">{"★".repeat(n)}</span>;
}

/** Card-edge category badge wraps the canonical CategoryChip with the
 *  card's `mr-1.5` spacing. Single source of truth lives in
 *  StatusChips.tsx. */
function CategoryBadge({ category }: { category: string | null | undefined }) {
  return (
    <span className="mr-1.5 inline-flex">
      <CategoryChip category={category as "homework" | "review" | "classwork" | null | undefined} />
    </span>
  );
}

function Card({
  a,
  onOpenPopover,
  onOpenAudit,
}: {
  a: Assignment;
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
  onOpenAudit: (a: Assignment) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: String(a.id) });
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      style={{ opacity: isDragging ? 0.4 : 1 }}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("[data-chip]")) return;
        onOpenAudit(a);
      }}
      className="bg-white border border-gray-200 rounded p-2 mb-2 shadow-sm hover:shadow-md cursor-grab active:cursor-grabbing"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs text-gray-500 truncate flex items-center min-w-0">
          <CategoryBadge category={a.work_category ?? null} />
          <span className="truncate">{a.subject}</span>
        </div>
        <div className="flex items-center gap-1">
          {a.discuss_with_teacher_at && (
            <WorthAChatChip note={a.discuss_with_teacher_note} compact />
          )}
          <ReviewPracticeButton a={a} />
          <PriorityStar n={a.priority} />
        </div>
      </div>
      <div className="text-sm font-medium leading-tight">{a.title}</div>
      {a.title_en && a.title_en !== a.title && (
        <div className="text-xs text-gray-600 italic">→ {a.title_en}</div>
      )}
      <div className="flex items-center justify-between mt-1 gap-2">
        <div className="text-xs text-gray-500" title={a.due_or_date ?? ""}>{formatDate(a.due_or_date)}</div>
        <div className="flex items-center gap-1" data-chip onClick={(e) => e.stopPropagation()}>
          <span
            onClick={(e) => {
              e.stopPropagation();
              onOpenPopover(a, (e.currentTarget as HTMLElement).getBoundingClientRect());
            }}
          >
            <EffectiveStatusChip a={a} />
          </span>
          <QuickActions a={a} />
        </div>
      </div>
      {a.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {a.tags.map((t) => (
            <span key={t} className="px-1.5 py-0 rounded-full border border-gray-200 bg-gray-50 text-[10px] text-gray-700">
              {t}
            </span>
          ))}
        </div>
      )}
      {a.attachments && a.attachments.length > 0 && (
        <div className="text-xs text-blue-700 mt-1">📎 {a.attachments.length} file{a.attachments.length > 1 ? "s" : ""}</div>
      )}
    </div>
  );
}

function Column({
  def,
  items,
  onOpenPopover,
  onOpenAudit,
}: {
  def: { key: ColumnKey; label: string; accent: string };
  items: Assignment[];
  onOpenPopover: (a: Assignment, rect: DOMRect) => void;
  onOpenAudit: (a: Assignment) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: def.key });
  return (
    <div
      ref={setNodeRef}
      className={`flex-1 min-w-[220px] rounded-lg border ${def.accent} p-3 ${isOver ? "ring-2 ring-blue-400" : ""}`}
    >
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-semibold text-gray-800">{def.label}</h4>
        <span className="text-xs text-gray-500">{items.length}</span>
      </div>
      <div className="min-h-[20px]">
        {items.map((a) => (
          <Card key={a.id} a={a} onOpenPopover={onOpenPopover} onOpenAudit={onOpenAudit} />
        ))}
        {items.length === 0 && (
          <div className="text-xs text-gray-400 py-4 text-center">Nothing here</div>
        )}
      </div>
    </div>
  );
}

export default function ChildBoard() {
  const { id } = useParams();
  const childId = Number(id);
  const qc = useQueryClient();
  const optimisticPatch = useOptimisticPatch();

  const { data, isLoading, error } = useQuery({
    queryKey: ["assignments-board", childId],
    queryFn: () => api.assignments({ child_id: childId }),
    enabled: !isNaN(childId),
  });

  const [popover, setPopover] = useState<{ a: Assignment; rect: DOMRect } | null>(null);
  const [audit, setAudit] = useState<Assignment | null>(null);
  const [dragging, setDragging] = useState<Assignment | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  if (isLoading) {
    return (
      <div>
        <ChildHeader title="Board" />
        <div className="flex gap-3 overflow-x-auto">
          <SkeletonBoardColumn />
          <SkeletonBoardColumn />
          <SkeletonBoardColumn />
          <SkeletonBoardColumn />
        </div>
      </div>
    );
  }
  if (error) return <div className="text-red-700">Error: {String(error)}</div>;
  if (!data) return null;

  const grouped: Record<ColumnKey, Assignment[]> = {
    not_started: [], in_progress: [], done_at_home: [], submitted: [], graded: [],
  };
  for (const a of data) grouped[columnFor(a)].push(a);
  for (const k of Object.keys(grouped) as ColumnKey[]) {
    grouped[k].sort((x, y) => {
      if (y.priority !== x.priority) return y.priority - x.priority;
      return (x.due_or_date || "").localeCompare(y.due_or_date || "");
    });
  }

  const onStart = (e: DragStartEvent) => {
    const a = data.find((x) => String(x.id) === String(e.active.id));
    setDragging(a ?? null);
  };

  const onEnd = async (e: DragEndEvent) => {
    setDragging(null);
    if (!e.over) return;
    const col = e.over.id as ColumnKey;
    const a = data.find((x) => String(x.id) === String(e.active.id));
    if (!a) return;
    const target = COLUMN_TO_PARENT_STATUS[col];
    if (target === "GRADED_NOOP") return; // can't move to graded manually
    if (a.parent_status === target) return;
    await optimisticPatch(a.id, { parent_status: target }, {
      label: target ? `Moved to ${target.replace(/_/g, " ")}` : "Cleared status",
    });
  };

  return (
    <div>
      <ChildHeader title="Board" />
      <div className="text-xs text-gray-500 mb-3">
        Drag cards between columns · click status chip to edit priority/snooze/tags · click card for timeline
      </div>

      <WorthAChatTray childId={childId} onOpenAudit={(a) => setAudit(a)} />

      <DndContext sensors={sensors} onDragStart={onStart} onDragEnd={onEnd}>
        <div className="flex gap-3 overflow-x-auto pb-4">
          {COLUMN_DEFS.map((def) => (
            <Column
              key={def.key}
              def={def}
              items={grouped[def.key]}
              onOpenPopover={(a, r) => setPopover({ a, rect: r })}
              onOpenAudit={(a) => setAudit(a)}
            />
          ))}
        </div>
        <DragOverlay>
          {dragging && (
            <div className="bg-white border border-gray-300 rounded p-2 shadow-lg text-sm">
              <div className="text-xs text-gray-500">{dragging.subject}</div>
              <div className="font-medium">{dragging.title}</div>
              {dragging.title_en && dragging.title_en !== dragging.title && (
                <div className="text-xs text-gray-600 italic">→ {dragging.title_en}</div>
              )}
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {popover && (
        <StatusPopover a={popover.a} anchorRect={popover.rect}
          onClose={() => setPopover(null)} onSaved={() => qc.invalidateQueries()} />
      )}
      {audit && <AuditDrawer a={audit} onClose={() => setAudit(null)} />}
    </div>
  );
}
