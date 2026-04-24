import { Link, NavLink, Route, Routes } from "react-router-dom";
import Today from "./pages/Today";
import Notifications from "./pages/Notifications";
import Settings from "./pages/Settings";
import ChildDetail from "./pages/ChildDetail";
import ChildGrades from "./pages/ChildGrades";
import ChildAssignments from "./pages/ChildAssignments";
import ChildComments from "./pages/ChildComments";
import ChildSyllabus from "./pages/ChildSyllabus";
import Messages from "./pages/Messages";
import Notes from "./pages/Notes";
import Summaries from "./pages/Summaries";
import SettingsChannels from "./pages/SettingsChannels";
import SettingsSyllabus from "./pages/SettingsSyllabus";
import AttachmentsPage from "./pages/AttachmentsPage";

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        "hover:text-blue-700 " + (isActive ? "text-blue-700 font-semibold" : "text-gray-700")
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between">
          <Link to="/" className="text-xl font-bold tracking-tight text-gray-900">
            🏫 Parent Cockpit
          </Link>
          <nav className="flex gap-5 text-sm">
            <NavItem to="/" label="Today" />
            <NavItem to="/messages" label="Messages" />
            <NavItem to="/attachments" label="Files" />
            <NavItem to="/notes" label="Notes" />
            <NavItem to="/summaries" label="Summaries" />
            <NavItem to="/notifications" label="Notifications" />
            <NavItem to="/settings" label="Settings" />
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-6xl mx-auto w-full px-5 py-6">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/child/:id" element={<ChildDetail />} />
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
        </Routes>
      </main>
    </div>
  );
}
