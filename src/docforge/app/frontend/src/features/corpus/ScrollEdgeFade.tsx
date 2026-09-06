// ====== Code Summary ======
// A subtle trailing-edge gradient hinting that the corpus grid has more columns off-screen —
// token-only (color-mix over the surface variable, no hardcoded hex), fades in/out with `visible`.

import { theme } from "../../theme";

interface ScrollEdgeFadeProps {
  visible: boolean;
  /** Distance from the container's right edge — the sticky "__actions" column's own width, since
   *  that column no longer scrolls away and the actual crop boundary now sits just before it. */
  inset?: number;
}

export function ScrollEdgeFade({ visible, inset = 0 }: ScrollEdgeFadeProps) {
  return (
    <div
      aria-hidden
      style={{
        position: "absolute", top: 0, bottom: 0, right: inset, width: 48,
        background: `linear-gradient(to right, transparent, color-mix(in srgb, ${theme.color.surface} 88%, transparent))`,
        opacity: visible ? 1 : 0, transition: "opacity .15s ease",
        pointerEvents: "none",
      }}
    />
  );
}
