// ====== Code Summary ======
// Whether the viewport is compact/touch — the same breakpoint the sidebar uses
// (`(max-width: 640px), (pointer: coarse)`). On a compact viewport the corpus grid stops pinning its
// row-actions column `sticky; right: 0`: that pin keeps delete/reingest reachable at a wide column
// count on desktop, but on a narrow screen the opaque ~140px column floats over the data columns
// scrolling underneath it and reads as a misplaced white panel on the right. Non-sticky there, the
// actions column simply scrolls into view like any other.

import { useEffect, useState } from "react";

const COMPACT_QUERY = "(max-width: 640px), (pointer: coarse)";

/** True when the viewport is narrow or touch-first — SSR/no-matchMedia safe (defaults to false). */
export function useCompactViewport(): boolean {
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    // 1. Guard environments without matchMedia (SSR, jsdom without the shim).
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;

    // 2. Track the query and keep local state in sync with viewport/pointer changes.
    const mql = window.matchMedia(COMPACT_QUERY);
    setCompact(mql.matches);
    const onChange = (e: MediaQueryListEvent) => setCompact(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return compact;
}
