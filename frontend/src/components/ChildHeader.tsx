import { Link, NavLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import ChildSwitcher from "./ChildSwitcher";

// Five tabs (within Miller 7±2). The kanban board lives at
// /child/:id/board and is reachable from CommandPalette / direct URL,
// but it's been unlinked from this sub-nav so every kid page isn't a
// 6-tab choice. See plan Layer 3 for rationale.
const SUB_SECTIONS: { to: string; label: string }[] = [
  { to: "",             label: "Overview"    },
  { to: "/assignments", label: "Assignments" },
  { to: "/grades",      label: "Grades"      },
  { to: "/comments",    label: "Comments"    },
  { to: "/syllabus",    label: "Syllabus"    },
];

/** Shared header for every /child/:id/* page — persistent child switcher
 * (left) and sub-section tabs (right). Tabs preserve the ? part of a URL
 * so switching kid keeps the same section. */
export default function ChildHeader({ title }: { title: string }) {
  const { id } = useParams();
  const childId = Number(id);
  const { data: children } = useQuery({ queryKey: ["children"], queryFn: api.children });
  const me = children?.find((c) => c.id === childId);

  return (
    <div className="mb-5">
      <div className="flex items-baseline justify-between gap-2 sm:gap-3 flex-wrap">
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap min-w-0">
          <Link to="/" className="text-gray-400 hover:text-gray-700 text-sm whitespace-nowrap">← Today</Link>
          <h2 className="text-xl sm:text-2xl font-bold truncate">{title}</h2>
          {me && (
            <span className="text-xs sm:text-sm px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-200 whitespace-nowrap">
              {me.display_name}
              {me.class_section && (
                <span className="text-gray-500 ml-1">· {me.class_section}</span>
              )}
            </span>
          )}
          <ChildSwitcher />
        </div>
      </div>
      {/* Sub-section nav — horizontally scrollable on narrow screens
          so the six tabs don't wrap into a multi-row mess. */}
      <nav className="flex gap-1 mt-3 border-b border-gray-200 overflow-x-auto -mx-1 px-1">
        {SUB_SECTIONS.map((s) => (
          <NavLink
            key={s.to}
            to={`/child/${childId}${s.to}`}
            end
            className={({ isActive }) =>
              "px-3 py-2 text-sm border-b-2 -mb-px transition-colors whitespace-nowrap " +
              (isActive
                ? "border-blue-700 text-blue-700 font-semibold"
                : "border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300")
            }
          >
            {s.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
