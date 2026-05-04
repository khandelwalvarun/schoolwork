/**
 * RecentClassworkCard — informational view of work the school
 * reported as done in class. Read-only: no parent_status, no
 * QuickActions, no AI button. The point is to know WHAT was
 * covered, not to track or action it.
 *
 * Renders as a collapsible details element (closed by default)
 * matching the Analytics block on ChildDetail.
 */
import { useQuery } from "@tanstack/react-query";
import { Assignment } from "../api";
import { formatDate } from "../util/dates";
import TitleBlock from "./TitleBlock";

export function RecentClassworkCard({
  childId,
  days = 30,
}: {
  childId: number;
  days?: number;
}) {
  const { data, isLoading } = useQuery<Assignment[]>({
    queryKey: ["classwork", childId, days],
    queryFn: () =>
      fetch(`/api/classwork?child_id=${childId}&days=${days}`).then((r) =>
        r.json(),
      ),
  });

  const count = data?.length ?? 0;
  return (
    <details className="surface mb-6 group">
      <summary className="px-4 py-3 cursor-pointer flex items-center gap-2 text-sm select-none">
        <span
          className="text-gray-400 transition-transform group-open:rotate-90 inline-block w-3"
          aria-hidden
        >
          ▶
        </span>
        <span className="font-semibold text-gray-700">📚 Recent classwork</span>
        <span className="text-xs text-gray-500">
          · {isLoading ? "loading…" : `${count} item${count === 1 ? "" : "s"} · last ${days} days · informational`}
        </span>
      </summary>
      <div className="border-t border-[color:var(--line-soft)] px-4 py-3">
        {isLoading ? (
          <div className="text-sm text-gray-500 italic">Loading…</div>
        ) : count === 0 ? (
          <div className="text-sm text-gray-500 italic">
            No classwork rows in the last {days} days. Either nothing's been
            reported yet or the school hasn't posted to Veracross.
          </div>
        ) : (
          <ClassworkList rows={data!} />
        )}
      </div>
    </details>
  );
}

function ClassworkList({ rows }: { rows: Assignment[] }) {
  // Group by date for quick visual scanning.
  const byDate = new Map<string, Assignment[]>();
  for (const r of rows) {
    const d = r.due_or_date || "(no date)";
    if (!byDate.has(d)) byDate.set(d, []);
    byDate.get(d)!.push(r);
  }
  const dates = Array.from(byDate.keys()).sort().reverse();
  return (
    <div className="space-y-3">
      {dates.map((d) => (
        <section key={d}>
          <h4 className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">
            {formatDate(d)}
          </h4>
          <ul className="space-y-1.5">
            {byDate.get(d)!.map((row) => (
              <li
                key={row.id}
                className="text-sm flex items-start gap-3 px-2 py-1.5 rounded border border-gray-100 bg-gray-50/50"
              >
                <span className="text-gray-500 text-xs whitespace-nowrap shrink-0 w-32 truncate">
                  {row.subject}
                </span>
                <div className="flex-1 min-w-0">
                  <TitleBlock
                    title={row.title}
                    titleEn={row.title_en}
                    className="truncate"
                  />
                  {row.body && (
                    <div className="text-xs text-gray-600 mt-0.5 line-clamp-2">
                      {row.body}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
