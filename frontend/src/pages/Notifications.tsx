import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

type Notif = { channel: string; status: string; error?: string; delivered_at?: string };
type Event = {
  id: number;
  kind: string;
  child_id: number | null;
  subject: string | null;
  notability: number;
  dedup_key: string;
  created_at: string;
  payload: Record<string, unknown>;
  notifications: Notif[];
};

export default function Notifications() {
  const { data, isLoading } = useQuery({ queryKey: ["notifications"], queryFn: () => api.notifications(14) });
  if (isLoading) return <div>Loading…</div>;
  const events = (data || []) as Event[];
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Notifications</h2>
      <table className="w-full text-sm bg-white border border-gray-200 rounded shadow-sm">
        <thead>
          <tr className="text-left text-gray-500 text-xs uppercase border-b border-gray-100">
            <th className="py-2 px-3 font-medium">When</th>
            <th className="py-2 px-3 font-medium">Kind</th>
            <th className="py-2 px-3 font-medium">Notability</th>
            <th className="py-2 px-3 font-medium">Child</th>
            <th className="py-2 px-3 font-medium">Subject</th>
            <th className="py-2 px-3 font-medium">Channels</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id} className="border-t border-gray-100 hover:bg-gray-50 align-top">
              <td className="py-2 px-3 text-gray-500 whitespace-nowrap">{new Date(e.created_at).toLocaleString()}</td>
              <td className="py-2 px-3 font-mono text-xs">{e.kind}</td>
              <td className="py-2 px-3">{e.notability.toFixed(2)}</td>
              <td className="py-2 px-3">{e.child_id ?? "—"}</td>
              <td className="py-2 px-3 text-gray-600">{e.subject}</td>
              <td className="py-2 px-3 space-x-2">
                {e.notifications.map((n, i) => (
                  <span key={i} className={`chip-${n.status === "sent" ? "green" : n.status === "failed" ? "red" : "amber"}`}>
                    {n.channel}: {n.status}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
