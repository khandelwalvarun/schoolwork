import { Link, NavLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import ChildSwitcher from "./ChildSwitcher";

const SUB_SECTIONS: { to: string; label: string }[] = [
  { to: "",            label: "Overview"    },
  { to: "/board",      label: "Board"       },
  { to: "/assignments", label: "Assignments" },
  { to: "/grades",     label: "Grades"      },
  { to: "/comments",   label: "Comments"    },
  { to: "/syllabus",   label: "Syllabus"    },
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
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <Link to="/" className="text-gray-400 hover:text-gray-700 text-sm">← Today</Link>
          <h2 className="text-2xl font-bold">{title}</h2>
          {me && (
            <span className="text-sm px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-200">
              {me.display_name}
              {me.class_section && (
                <span className="text-gray-500 ml-1">· {me.class_section}</span>
              )}
            </span>
          )}
          <ChildSwitcher />
        </div>
      </div>
      <nav className="flex gap-1 mt-3 border-b border-gray-200">
        {SUB_SECTIONS.map((s) => (
          <NavLink
            key={s.to}
            to={`/child/${childId}${s.to}`}
            end
            className={({ isActive }) =>
              "px-3 py-2 text-sm border-b-2 -mb-px transition-colors " +
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
