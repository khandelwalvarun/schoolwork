import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

export default function Notes() {
  const qc = useQueryClient();
  const { data: children } = useQuery({ queryKey: ["children"], queryFn: api.children });
  const { data: notes } = useQuery({ queryKey: ["notes"], queryFn: () => api.notes() });
  const [text, setText] = useState("");
  const [childId, setChildId] = useState<string>("");
  const [tags, setTags] = useState("");

  const add = async () => {
    if (!text.trim()) return;
    await api.addNote(text, childId ? Number(childId) : undefined, tags || undefined);
    setText("");
    setTags("");
    qc.invalidateQueries({ queryKey: ["notes"] });
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Parent notes</h2>

      <section className="bg-white border border-gray-200 rounded shadow-sm p-4 mb-6">
        <h3 className="font-semibold mb-2">New note</h3>
        <textarea
          rows={3}
          className="w-full border border-gray-300 rounded p-2 text-sm"
          placeholder="e.g., called Samarth's homeroom about PE kit on 2026-04-20"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex gap-2 mt-2 text-sm">
          <select className="border border-gray-300 rounded px-2 py-1" value={childId} onChange={(e) => setChildId(e.target.value)}>
            <option value="">All / none</option>
            {(children || []).map((c) => <option key={c.id} value={c.id}>{c.display_name}</option>)}
          </select>
          <input
            className="border border-gray-300 rounded px-2 py-1 flex-1"
            placeholder="tags (comma-separated)"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
          <button className="bg-blue-700 text-white text-sm rounded px-3 py-1 hover:bg-blue-800" onClick={add}>
            Save
          </button>
        </div>
      </section>

      <section className="space-y-3">
        {(notes || []).length === 0 && <div className="text-gray-500">No notes yet.</div>}
        {(notes || []).map((n) => {
          const kid = children?.find((c) => c.id === n.child_id);
          return (
            <div key={n.id} className="bg-white border border-gray-200 rounded shadow-sm p-3">
              <div className="flex items-baseline justify-between">
                <div className="text-xs text-gray-500">
                  {n.note_date} {kid && `· ${kid.display_name}`}
                  {n.tags && <span className="ml-2 text-gray-500">[{n.tags}]</span>}
                </div>
              </div>
              <div className="text-sm mt-1 whitespace-pre-wrap">{n.note}</div>
            </div>
          );
        })}
      </section>
    </div>
  );
}
