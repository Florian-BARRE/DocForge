// ====== Code Summary ======
// A subtle trailing-edge gradient hinting that the corpus grid has more columns off-screen —
// token-only (color-mix over the surface variable, no hardcoded hex), fades in/out with `visible`.

import { theme } from "../../theme";

export function ScrollEdgeFade({ visible }: { visible: boolean }) {
  return (
    <div
      aria-hidden
      style={{
        position: "absolute", top: 0, bottom: 0, right: 0, width: 48,
        background: `linear-gradient(to right, transparent, color-mix(in srgb, ${theme.color.surface} 88%, transparent))`,
        opacity: visible ? 1 : 0, transition: "opacity .15s ease",
        pointerEvents: "none",
      }}
    />
  );
}
