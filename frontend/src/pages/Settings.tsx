import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function Settings() {
  const { data } = useQuery({ queryKey: ["channel-config"], queryFn: api.channelConfig });
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Settings</h2>
      <section className="bg-white border border-gray-200 rounded shadow-sm p-5">
        <h3 className="font-semibold mb-3">Channel policy</h3>
        <pre className="text-xs bg-gray-50 p-3 rounded border border-gray-100 overflow-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
        <p className="text-xs text-gray-500 mt-3">
          Edit via <code>PUT /api/channel-config</code> or the MCP <code>update_channel_config</code> tool.
        </p>
      </section>
    </div>
  );
}
