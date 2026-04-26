/**
 * useFloatingPosition — clamps a popover/dropdown so it never spills past
 * the viewport edges.
 *
 * Pattern:
 *   - Given an anchor `DOMRect` (the trigger button's bounding rect),
 *     pick a "natural" position (default: directly below the anchor,
 *     left-aligned). After the floating element mounts, measure it,
 *     then nudge top/left so the whole thing fits in the viewport.
 *
 *   - If the floating would overflow the right edge, shift left so its
 *     right edge sits at `viewportWidth - margin`.
 *   - If it would overflow the bottom edge, flip above the anchor.
 *   - Same for left + top edges.
 *
 *   - Re-measures on resize.
 *
 * Returns the absolute style object the caller spreads into the
 * floating element's `style`.
 */
import { useLayoutEffect, useRef, useState, RefObject } from "react";

export type FloatingPosition = {
  top: number;
  left: number;
  /** Set to position so its right is fixed (use with right: number). */
  right?: number;
  /** True when the floating is rendered above the anchor instead of below. */
  flippedAbove?: boolean;
};

const MARGIN = 8;

export function useFloatingPosition(
  anchor: DOMRect | null,
  floatingRef: RefObject<HTMLElement | null>,
): FloatingPosition | null {
  const [pos, setPos] = useState<FloatingPosition | null>(null);
  const lastAnchor = useRef<DOMRect | null>(null);
  lastAnchor.current = anchor;

  useLayoutEffect(() => {
    if (!anchor || !floatingRef.current) {
      setPos(null);
      return;
    }
    const recompute = () => {
      const a = lastAnchor.current;
      const el = floatingRef.current;
      if (!a || !el) return;
      const fw = el.offsetWidth;
      const fh = el.offsetHeight;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      // Natural position: below anchor, left-aligned.
      let top = a.bottom + window.scrollY + 4;
      let left = a.left + window.scrollX;
      let flippedAbove = false;

      // Horizontal clamp: prefer left-align; if overflowing right, shift left.
      if (left + fw > window.scrollX + vw - MARGIN) {
        left = Math.max(window.scrollX + MARGIN, window.scrollX + vw - fw - MARGIN);
      }
      if (left < window.scrollX + MARGIN) {
        left = window.scrollX + MARGIN;
      }

      // Vertical: prefer below; if it would overflow bottom, flip above.
      if (top + fh > window.scrollY + vh - MARGIN) {
        const aboveTop = a.top + window.scrollY - fh - 4;
        if (aboveTop >= window.scrollY + MARGIN) {
          top = aboveTop;
          flippedAbove = true;
        } else {
          // Neither below nor above fits — clamp to viewport top so it's at
          // least visible and the user can scroll it.
          top = Math.max(window.scrollY + MARGIN, window.scrollY + vh - fh - MARGIN);
        }
      }
      setPos({ top, left, flippedAbove });
    };
    recompute();
    window.addEventListener("resize", recompute);
    window.addEventListener("scroll", recompute, true);
    return () => {
      window.removeEventListener("resize", recompute);
      window.removeEventListener("scroll", recompute, true);
    };
  }, [anchor, floatingRef]);

  return pos;
}
