import { Link, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/** Persistent child-switcher for any /child/:id/* page. Extracts the sub-section
 * (board | grades | assignments | comments | syllabus | '') from the URL and
 * regenerates it against every known child's id — so flipping kids keeps you
 * on the same page type. */
export default function ChildSwitcher() {
  const { id } = useParams();
  const loc = useLocation();
  const { data: children } = useQuery({ queryKey: ["children"], queryFn: api.children });

  // Extract the sub-section after /child/:id/
  const match = loc.pathname.match(/^\/child\/\d+(\/[a-z]+)?$/);
  const sub = (match?.[1] || "").replace(/^\//, "");  // "", "board", "grades", etc.

  if (!children || children.length < 2) return null;

  const currentId = Number(id);

  return (
    <div className="inline-flex gap-1 bg-gray-100 rounded-full p-0.5 text-sm">
      {children.map((c) => {
        const isActive = c.id === currentId;
        const target = sub ? `/child/${c.id}/${sub}` : `/child/${c.id}`;
        return (
          <Link
            key={c.id}
            to={target}
            className={
              "px-3 py-1 rounded-full transition-colors " +
              (isActive
                ? "bg-white text-gray-900 shadow-sm font-medium"
                : "text-gray-600 hover:text-gray-900")
            }
          >
            {c.display_name}
            {c.class_section && (
              <span className="text-xs text-gray-400 ml-1">{c.class_section}</span>
            )}
          </Link>
        );
      })}
    </div>
  );
}
