import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Today from "./pages/Today";
import Notifications from "./pages/Notifications";
import Settings from "./pages/Settings";
import ChildDetail from "./pages/ChildDetail";
import ChildGrades from "./pages/ChildGrades";
import ChildAssignments from "./pages/ChildAssignments";
import ChildBoard from "./pages/ChildBoard";
import ChildComments from "./pages/ChildComments";
import ChildSyllabus from "./pages/ChildSyllabus";
import Messages from "./pages/Messages";
import Notes from "./pages/Notes";
import Summaries from "./pages/Summaries";
import SettingsChannels from "./pages/SettingsChannels";
import SettingsSyllabus from "./pages/SettingsSyllabus";
import SettingsVeracross from "./pages/SettingsVeracross";
import AttachmentsPage from "./pages/AttachmentsPage";
import CommandPalette from "./components/CommandPalette";
import HelpPanel from "./components/HelpPanel";
import SyncStatusBar from "./components/SyncStatusBar";
import { api } from "./api";

function NavItem({ to, label, end = true }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        "hover:text-blue-700 " + (isActive ? "text-blue-700 font-semibold" : "text-gray-700")
      }
    >
      {label}
    </NavLink>
  );
}

function ChildNavLink({ id, name }: { id: number; name: string }) {
  // Active on any /child/:id* page, not just /child/:id.
  return (
    <NavLink
      to={`/child/${id}`}
      className={({ isActive }) =>
        "hover:text-blue-700 " + (isActive ? "text-blue-700 font-semibold" : "text-gray-700")
      }
    >
      {name}
    </NavLink>
  );
}

export default function App() {
  const { data: children } = useQuery({ queryKey: ["children"], queryFn: api.children });

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Link to="/" className="text-xl font-bold tracking-tight text-gray-900">
              🏫 Parent Cockpit
            </Link>
            <button
              onClick={() => {
                // Simulate ⌘K press
                const ev = new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true });
                document.dispatchEvent(ev);
              }}
              className="text-xs text-gray-500 hover:text-gray-800 inline-flex items-center gap-1 border border-[color:var(--line)] rounded px-2 py-0.5 bg-[color:var(--bg-muted)]"
              title="Search assignments, kids, pages, actions"
            >
              <span>Search</span>
              <span className="kbd">⌘K</span>
            </button>
          </div>
          <nav className="flex gap-5 text-sm items-center flex-wrap">
            <NavItem to="/" label="Today" />
            {(children || []).map((c) => (
              <ChildNavLink key={c.id} id={c.id} name={c.display_name} />
            ))}
            <span className="text-gray-300">|</span>
            <NavItem to="/messages" label="Messages" />
            <NavItem to="/attachments" label="Files" />
            <NavItem to="/notes" label="Notes" />
            <NavItem to="/summaries" label="Summaries" />
            <NavItem to="/notifications" label="Notifications" />
            <NavItem to="/settings" label="Settings" />
            <button
              onClick={() => document.dispatchEvent(new CustomEvent("pc:help:toggle"))}
              className="text-xs text-gray-500 hover:text-gray-800 inline-flex items-center gap-1 border border-[color:var(--line)] rounded-full w-6 h-6 justify-center bg-[color:var(--bg-muted)]"
              title="Keyboard shortcuts & tips (? key)"
              aria-label="Help"
            >
              ?
            </button>
          </nav>
        </div>
      </header>
      <SyncStatusBar />
      <CommandPalette />
      <HelpPanel />
      <main className="flex-1 max-w-6xl mx-auto w-full px-5 py-6">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/child/:id" element={<ChildDetail />} />
          <Route path="/child/:id/board" element={<ChildBoard />} />
          <Route path="/child/:id/grades" element={<ChildGrades />} />
          <Route path="/child/:id/assignments" element={<ChildAssignments />} />
          <Route path="/child/:id/comments" element={<ChildComments />} />
          <Route path="/child/:id/syllabus" element={<ChildSyllabus />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/attachments" element={<AttachmentsPage />} />
          <Route path="/notes" element={<Notes />} />
          <Route path="/summaries" element={<Summaries />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/settings/channels" element={<SettingsChannels />} />
          <Route path="/settings/syllabus" element={<SettingsSyllabus />} />
          <Route path="/settings/veracross" element={<SettingsVeracross />} />
        </Routes>
      </main>
    </div>
  );
}
