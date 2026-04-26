import { useEffect, useState } from "react";

/** Keyboard-shortcut + feature-cheat-sheet overlay.
 *   Open via `?` (global hotkey — ignored while typing in an input/textarea)
 *   or the "?" button in the nav. */
export default function HelpPanel() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement | null)?.isContentEditable;
      if (!typing && e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      } else if (e.key.toLowerCase() === "h" && (e.metaKey || e.ctrlKey) && e.shiftKey) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Expose a way for the nav button to open it
  useEffect(() => {
    function onCustom(e: Event) {
      if ((e as CustomEvent).type === "pc:help:toggle") setOpen((v) => !v);
    }
    document.addEventListener("pc:help:toggle", onCustom as EventListener);
    return () => document.removeEventListener("pc:help:toggle", onCustom as EventListener);
  }, []);

  if (!open) return null;

  const Row = ({ label, keys }: { label: string; keys: string[] }) => (
    <div className="flex items-center justify-between py-1.5 text-sm border-b border-[color:var(--line-soft)]">
      <span>{label}</span>
      <span className="flex gap-1">
        {keys.map((k, i) => <span key={i} className="kbd">{k}</span>)}
      </span>
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-[70] flex items-start justify-center pt-[10vh] fade-in"
      style={{ background: "rgba(0,0,0,0.4)" }}
      onClick={() => setOpen(false)}
    >
      <div
        className="w-[680px] max-w-[92vw] bg-white rounded-xl shadow-2xl border border-[color:var(--line)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--line)]">
          <h3 className="text-lg font-semibold">Shortcuts & tips</h3>
          <button onClick={() => setOpen(false)} className="text-2xl text-gray-400 hover:text-gray-700 leading-none">×</button>
        </div>
        <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-4">
          <div>
            <div className="h-section mb-2">Navigation</div>
            <Row label="Open command palette"  keys={["⌘", "K"]} />
            <Row label="Skip to content"       keys={["Tab"]} />
            <Row label="Close any dialog"      keys={["Esc"]} />
            <Row label="Open this help"        keys={["?"]} />
          </div>

          <div>
            <div className="h-section mb-2">List shortcuts (j/k everywhere)</div>
            <Row label="Next row"               keys={["j"]} />
            <Row label="Previous row"           keys={["k"]} />
            <Row label="Open audit drawer"      keys={["Enter"]} />
            <Row label="Toggle selection"       keys={["x"]} />
            <Row label="Mark done at home"      keys={["e"]} />
            <Row label="Snooze (open menu)"     keys={["s"]} />
            <Row label="Undo last action"       keys={["Z"]} />
          </div>

          <div>
            <div className="h-section mb-2">Per-row quick actions</div>
            <Row label="Toggle done at home"   keys={["☐"]} />
            <Row label="Snooze (menu)"          keys={["💤"]} />
            <Row label="Full status popover"    keys={["⋯"]} />
            <Row label="Open audit timeline"    keys={["click row"]} />
          </div>

          <div>
            <div className="h-section mb-2">Bulk editing</div>
            <Row label="Select one"             keys={["☑"]} />
            <Row label="Select all in bucket"   keys={["header ☑"]} />
            <Row label="Deselect"               keys={["✕ in bar"]} />
            <Row label="Bulk mark done"         keys={["✓ Done"]} />
            <Row label="Bulk snooze preset"     keys={["💤 Snooze ▾"]} />
            <Row label="Bulk set priority"      keys={["★ Priority ▾"]} />
            <Row label="Bulk set status"        keys={["Status ▾"]} />
          </div>

          <div>
            <div className="h-section mb-2">Buckets</div>
            <Row label="Expand/collapse"        keys={["click header"]} />
            <Row label="Reorder (per kid)"      keys={["drag ⋮⋮"]} />
            <div className="text-xs text-gray-500 mt-2">
              Collapsed state and bucket order are saved to the server
              (<code>data/ui_prefs.json</code>) and survive reloads.
            </div>
          </div>

          <div className="md:col-span-2">
            <div className="h-section mb-2">Status precedence</div>
            <div className="text-xs text-gray-600 leading-relaxed">
              Effective status (the chip label) is chosen top-to-bottom:
              <span className="ml-2 text-gray-800">
                graded → submitted → done_at_home → in_progress → needs_help → blocked → skipped → overdue → pending
              </span>.
              Portal and parent states co-exist — the portal wins for
              <span className="chip-green mx-1">graded</span>, parent wins for everything else
              until Veracross catches up.
            </div>
          </div>

          <div className="md:col-span-2">
            <div className="h-section mb-2">Automation</div>
            <ul className="text-xs text-gray-600 list-disc pl-5 space-y-1">
              <li>Hourly portal sync, 08:00–22:00 IST — toggleable in Settings.</li>
              <li>Daily digest at 16:00 IST · Weekly digest Sunday 20:00.</li>
              <li>Weekly syllabus recheck, Sunday 07:30 — fires an event when anything changed.</li>
              <li>Attachments auto-downloaded to <code>data/attachments/</code>; served at <code>/api/attachments/&#123;id&#125;</code>.</li>
            </ul>
          </div>
        </div>
        <div className="px-5 py-2 border-t border-[color:var(--line-soft)] text-xs text-gray-500 flex justify-between">
          <span>Press <span className="kbd">?</span> to toggle · <span className="kbd">Esc</span> to close</span>
          <a href="/docs" target="_blank" className="text-blue-700 hover:underline">API docs</a>
        </div>
      </div>
    </div>
  );
}
