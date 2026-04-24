import { useEffect, useRef, useState } from "react";

/** Remote login modal — runs a headless Chromium on the server, streams
 * screenshots to the parent's browser, forwards click/type/key events.
 *
 * The browser window appears entirely inside the modal so the parent can
 * solve Veracross's reCAPTCHA from any LAN device. On success, the session
 * cookies (including the non-persistent `_veracross_session`) are saved
 * to `recon/storage_state.json` so subsequent headless scrapes work.
 */
type LoginStatus = {
  id?: string;
  status: string;
  message?: string;
  url?: string | null;
  viewport?: { width: number; height: number };
  shot_at?: number;
};

type Check = { logged_in?: boolean; url?: string; ok?: boolean; error?: string };

const VW = 1280;
const VH = 900;

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    headers: opts?.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export default function RemoteLoginModal({ onClose }: { onClose: () => void }) {
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [imgSrc, setImgSrc] = useState<string>("");
  const [status, setStatus] = useState<LoginStatus>({ status: "starting" });
  const [banner, setBanner] = useState<string>("");
  const [saved, setSaved] = useState(false);

  // Start a session on mount, close on unmount
  useEffect(() => {
    (async () => {
      try {
        const s = await fetchJson<LoginStatus>("/api/veracross/login/start", { method: "POST" });
        setStatus(s);
      } catch (e) {
        setBanner(`Start failed: ${String(e)}`);
      }
    })();
    return () => {
      fetch("/api/veracross/login", { method: "DELETE" }).catch(() => { /* best-effort */ });
    };
  }, []);

  // Poll screenshot + status ~every 500ms while open
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        // cache-busting query so img refreshes
        setImgSrc(`/api/veracross/login/screenshot?t=${Date.now()}`);
        const s = await fetchJson<LoginStatus>("/api/veracross/login/status");
        setStatus(s);
      } catch { /* ignore transient */ }
      setTimeout(tick, 500);
    };
    tick();
    return () => { cancelled = true; };
  }, []);

  // Global key capture while modal is open — forward to backend page.keyboard
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA") {
        // Let the modal's own inputs (if any) behave normally
        return;
      }
      if (!imgRef.current?.matches(":hover") && document.activeElement !== imgRef.current) {
        // Only capture keys when the remote-browser image is focused/hovered
        if (e.key !== "Escape") return;
      }
      if (e.key === "Escape") {
        onClose();
        return;
      }
      // Printable: forward as text; special keys as key press
      if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        fetchJson("/api/veracross/login/type", {
          method: "POST",
          body: JSON.stringify({ text: e.key }),
        }).catch(() => {});
      } else if (["Backspace", "Enter", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) {
        e.preventDefault();
        fetchJson("/api/veracross/login/key", {
          method: "POST",
          body: JSON.stringify({ key: e.key }),
        }).catch(() => {});
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onImageClick = async (e: React.MouseEvent<HTMLImageElement>) => {
    if (!imgRef.current) return;
    const r = imgRef.current.getBoundingClientRect();
    const px = Math.round(((e.clientX - r.left) / r.width) * VW);
    const py = Math.round(((e.clientY - r.top) / r.height) * VH);
    try {
      await fetchJson("/api/veracross/login/click", {
        method: "POST",
        body: JSON.stringify({ x: px, y: py }),
      });
      // Auto-check success shortly after every click
      setTimeout(async () => {
        try {
          const c = await fetchJson<Check>("/api/veracross/login/check-success");
          if (c.logged_in) {
            setBanner("Login detected — saving session…");
            const r2 = await fetchJson<{ ok?: boolean; bytes?: number; error?: string }>(
              "/api/veracross/login/finish", { method: "POST" }
            );
            if (r2.ok) {
              setSaved(true);
              setBanner(`Session saved (${r2.bytes} bytes). Safe to close.`);
            } else {
              setBanner(`Save failed: ${r2.error}`);
            }
          }
        } catch { /* ignore */ }
      }, 800);
    } catch { /* ignore */ }
  };

  const autoFill = async () => {
    setBanner("Filling username + password…");
    const r = await fetchJson<{ ok?: boolean; error?: string }>(
      "/api/veracross/login/fill-credentials", { method: "POST" }
    );
    setBanner(r.ok ? "Filled. Solve the CAPTCHA and click Log In." : `Fill failed: ${r.error}`);
  };

  const manualSave = async () => {
    const c = await fetchJson<Check>("/api/veracross/login/check-success");
    if (!c.logged_in) {
      setBanner("Not logged in yet — finish signing in first.");
      return;
    }
    const r = await fetchJson<{ ok?: boolean; bytes?: number; error?: string }>(
      "/api/veracross/login/finish", { method: "POST" }
    );
    if (r.ok) {
      setSaved(true);
      setBanner(`Session saved (${r.bytes} bytes). Safe to close.`);
    } else {
      setBanner(`Save failed: ${r.error}`);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center fade-in"
      style={{ background: "rgba(0,0,0,0.6)" }}
    >
      <div className="bg-white rounded-xl shadow-2xl border border-[color:var(--line)] flex flex-col"
           style={{ width: "min(95vw, 1100px)", maxHeight: "95vh" }}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--line)]">
          <div>
            <h3 className="text-lg font-semibold">Veracross remote login</h3>
            <div className="text-xs text-gray-500 mt-0.5">
              Server runs headless Chromium · you solve the CAPTCHA here · session cookies save to
              <code className="mx-1">recon/storage_state.json</code>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={autoFill} className="text-xs px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
                    title="Auto-type the stored username + password">
              Auto-fill creds
            </button>
            <button onClick={manualSave} className="text-xs px-3 py-1 border border-emerald-300 bg-emerald-50 text-emerald-800 rounded hover:bg-emerald-100"
                    disabled={saved}>
              {saved ? "✓ Saved" : "I'm logged in — save session"}
            </button>
            <button onClick={onClose} className="text-2xl text-gray-400 hover:text-gray-700 leading-none">×</button>
          </div>
        </div>

        <div className="px-5 py-2 border-b border-[color:var(--line-soft)] text-xs flex items-center gap-3 flex-wrap">
          <span className={
            "px-2 py-0.5 rounded font-medium " +
            (status.status === "success" ? "bg-emerald-100 text-emerald-800"
             : status.status === "error" ? "bg-red-100 text-red-800"
             : "bg-gray-100 text-gray-700")
          }>
            {status.status}
          </span>
          {status.url && <span className="text-gray-500 truncate max-w-[560px]">{status.url}</span>}
          {banner && <span className="ml-auto text-gray-700">{banner}</span>}
        </div>

        <div className="flex-1 overflow-auto p-4 bg-gray-100" tabIndex={0}>
          {imgSrc ? (
            <img
              ref={imgRef}
              src={imgSrc}
              onClick={onImageClick}
              style={{ width: "100%", height: "auto", cursor: "crosshair" }}
              className="bg-white shadow-lg rounded border border-gray-300"
              alt="Remote browser"
              tabIndex={0}
            />
          ) : (
            <div className="text-center text-gray-500 py-16">Spawning browser…</div>
          )}
        </div>

        <div className="px-5 py-2 border-t border-[color:var(--line-soft)] text-xs text-gray-500">
          Click the image to click the page · printable keys while hovering the image type into it ·
          <span className="kbd ml-1">Esc</span> to close.
        </div>
      </div>
    </div>
  );
}
