/**
 * ClassworkTodayStrip — what the school reported as covered in class.
 *
 * Now built on the shared Tray primitive — same expand/collapse +
 * tone vocab as AnomalyTray + WorthAChatTray + ShakyTopicsTray. Sits
 * inside each kid section on Today; deliberately gray-toned so it
 * doesn't compete with the actionable trays above the kid blocks.
 *
 * Read-only and informational — classwork isn't actionable, so the
 * tray's leading icon is a small CategoryChip, and the row renderer
 * is intentionally quiet (date · subject · title).
 */
import { useQuery } from "@tanstack/react-query";
import { Assignment } from "../api";
import { Link } from "react-router-dom";
import { CategoryChip } from "./StatusChips";
import { Tray, trayLineClass } from "./Tray";
import { formatDate } from "../util/dates";

export function ClassworkTodayStrip({ childId }: { childId: number }) {
  // Pull last 7 days of classwork. 7 days hits the right balance:
  // covers the typical Mon–Fri school week, doesn't overwhelm.
  const { data } = useQuery<Assignment[]>({
    queryKey: ["classwork-strip", childId, 7],
    queryFn: () =>
      fetch(`/api/classwork?child_id=${childId}&days=7`).then((r) => r.json()),
    staleTime: 60_000,
  });

  const rows = data ?? [];
  if (rows.length === 0) return null;

  const today = new Date().toISOString().slice(0, 10);
  const todayRows = rows.filter((r) => r.due_or_date === today);
  const earlierRows = rows.filter((r) => r.due_or_date !== today);
  const todaySubjects = Array.from(
    new Set(todayRows.map((r) => r.subject || "").filter(Boolean)),
  );

  const summary =
    todayRows.length > 0
      ? `today · ${todayRows.length} item${todayRows.length === 1 ? "" : "s"}` +
        (todaySubjects.length > 0 ? ` · ${todaySubjects.join(" · ")}` : "")
      : `nothing today · ${earlierRows.length} this week`;

  return (
    <Tray
      title={
        <span className="inline-flex items-center gap-2">
          <CategoryChip category="classwork" />
          <span>In class</span>
        </span>
      }
      summary={summary}
      tone="gray"
      // Auto-expand when there's classwork TODAY — that's the moment
      // the parent wants to know "what did they do in class?". On
      // quiet days it stays collapsed so the kid block reads tighter.
      defaultCollapsed={todayRows.length === 0}
      rightSlot={
        <Link
          to={`/child/${childId}#classwork`}
          onClick={(e) => e.stopPropagation()}
          className="text-meta text-blue-700 hover:underline"
        >
          all classwork →
        </Link>
      }
    >
      <ul className="space-y-0.5">
        {todayRows.map((r) => (
          <ClassworkLine key={r.id} r={r} dateLabel="Today" />
        ))}
        {earlierRows.slice(0, 6).map((r) => (
          <ClassworkLine
            key={r.id}
            r={r}
            // Use the cockpit's standard formatDate (e.g. "Yesterday",
            // "3 days ago", "Mon 5 May") instead of the raw ISO.
            dateLabel={formatDate(r.due_or_date)}
          />
        ))}
        {earlierRows.length > 6 && (
          <li className="text-meta text-gray-500 pl-2">
            + {earlierRows.length - 6} more this week —{" "}
            <Link
              to={`/child/${childId}#classwork`}
              className="text-blue-700 hover:underline"
            >
              see all
            </Link>
          </li>
        )}
      </ul>
    </Tray>
  );
}

function ClassworkLine({ r, dateLabel }: { r: Assignment; dateLabel: string }) {
  return (
    <li className={trayLineClass("gray") + " flex items-baseline gap-2"}>
      <span
        className="text-meta text-gray-500 shrink-0 w-24 truncate"
        title={r.due_or_date ?? ""}
      >
        {dateLabel}
      </span>
      <span className="text-meta text-gray-500 shrink-0 w-20 truncate">{r.subject}</span>
      <span className="truncate text-body">{r.title}</span>
    </li>
  );
}
