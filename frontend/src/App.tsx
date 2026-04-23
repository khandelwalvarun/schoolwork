import { Link, Route, Routes } from "react-router-dom";
import Today from "./pages/Today";
import Notifications from "./pages/Notifications";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-5 py-4 flex items-center justify-between">
          <Link to="/" className="text-xl font-bold tracking-tight text-gray-900">
            🏫 Parent Cockpit
          </Link>
          <nav className="flex gap-5 text-sm">
            <Link className="hover:text-blue-700" to="/">Today</Link>
            <Link className="hover:text-blue-700" to="/notifications">Notifications</Link>
            <Link className="hover:text-blue-700" to="/settings">Settings</Link>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-5xl mx-auto w-full px-5 py-6">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
