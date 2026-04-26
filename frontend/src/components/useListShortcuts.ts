/**
 * useListShortcuts — Linear/Superhuman-style keyboard shortcuts for the
 * assignment lists. Binds at the document level; skips when typing in
 * inputs/textareas/contenteditables/the cmdk palette.
 *
 *   j           focus next visible row
 *   k           focus previous visible row
 *   Enter       click the focused row (opens audit drawer)
 *   x           toggle selection on the focused row (the SelectBox)
 *   e           click the "Mark done at home" button on the focused row
 *   s           click the "Snooze" button on the focused row (opens menu)
 *   ?           toggle help panel
 *
 * No state held inside React; uses document.activeElement and
 * focus/scrollIntoView to navigate. Cheap, lives outside the React tree.
 */
import { useEffect } from "react";

const ROW_SEL = '[role="row"][tabindex="0"]';

function isTyping(): boolean {
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return true;
  if ((el as HTMLElement).isContentEditable) return true;
  // Inside the cmdk palette? Skip.
  if (el.closest("[cmdk-root]")) return true;
  return false;
}

function visibleRows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(ROW_SEL))
    .filter((el) => el.offsetParent !== null);
}

function moveFocus(direction: 1 | -1): boolean {
  const rows = visibleRows();
  if (rows.length === 0) return false;
  const cur = document.activeElement as HTMLElement | null;
  const idx = cur ? rows.indexOf(cur) : -1;
  let next: HTMLElement;
  if (idx === -1) {
    next = direction > 0 ? rows[0] : rows[rows.length - 1];
  } else {
    const ni = (idx + direction + rows.length) % rows.length;
    next = rows[ni];
  }
  next.focus();
  next.scrollIntoView({ block: "nearest", behavior: "smooth" });
  return true;
}

function clickInRow(rowEl: HTMLElement, titleSubstr: string): boolean {
  const btn = Array.from(rowEl.querySelectorAll<HTMLButtonElement>("button"))
    .find((b) => (b.title || b.getAttribute("aria-label") || "").toLowerCase().includes(titleSubstr));
  if (!btn) return false;
  btn.click();
  return true;
}

export function useListShortcuts(): void {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTyping()) return;
      const k = e.key;
      const focused = document.activeElement as HTMLElement | null;
      const isInRow = focused?.matches(ROW_SEL);
      switch (k) {
        case "j":
          if (moveFocus(1)) e.preventDefault();
          return;
        case "k":
          if (moveFocus(-1)) e.preventDefault();
          return;
        case "Enter":
          if (isInRow) {
            e.preventDefault();
            focused!.click();
          }
          return;
        case "x":
          if (isInRow) {
            const cb = focused!.querySelector<HTMLInputElement>('input[type="checkbox"]');
            if (cb) {
              e.preventDefault();
              cb.click();
            }
          }
          return;
        case "e":
          if (isInRow) {
            e.preventDefault();
            clickInRow(focused!, "mark done");
          }
          return;
        case "s":
          if (isInRow) {
            e.preventDefault();
            clickInRow(focused!, "snooze");
          }
          return;
        // ? key already handled by HelpPanel; don't intercept here
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}
