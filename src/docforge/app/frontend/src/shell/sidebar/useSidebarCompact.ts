// ====== Code Summary ======
// Detects a "compact" viewport — narrow and/or touch-primary — where hover/focus-to-preview makes
// no sense: touch has no hover state, and on a narrow screen a 240px overlay eats most of it. Used
// by Sidebar to gate its transient hover/focus expansion: on a compact viewport the sidebar only
// ever expands via the deliberate pin toggle (always reachable, even collapsed — see
// SidebarFooter), never unannounced from a resting mouse/touch position.

import { useEffect, useState } from "react";

// Comma = OR in a media query list: a narrow viewport (checked responsively, not just at first
// paint) OR a coarse (touch) primary pointer, regardless of viewport width.
const COMPACT_QUERY = "(max-width: 640px), (pointer: coarse)";

function readCompact(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia(COMPACT_QUERY).matches;
}

export function useSidebarCompact(): boolean {
  const [compact, setCompact] = useState<boolean>(readCompact);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(COMPACT_QUERY);
    const onChange = () => setCompact(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return compact;
}
