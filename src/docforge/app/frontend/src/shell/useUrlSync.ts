// ====== Code Summary ======
// Layers URL<->state sync on top of the existing in-memory router: pushes the URL hash whenever
// `view` changes, and drives the same `setView` path on Back/Forward via `popstate`. Purely
// additive — App.tsx still owns `view`/`setView`, every page still just calls `onNavigate`.

import { useEffect, useRef } from "react";
import type { Navigate, View } from "./view";
import { parseViewFromHash, serializeViewToHash } from "./urlSync";

/**
 * Keep `window.location.hash` and the shell's View in sync, both ways.
 *
 * @param view - The shell's current view (owned by App.tsx's useState).
 * @param setView - The shell's navigate callback, reused so Back/Forward feel identical to a
 *                   normal in-app navigation.
 */
export function useUrlSync(view: View, setView: Navigate): void {
  const isFirstRun = useRef(true);

  useEffect(() => {
    const nextHash = `#${serializeViewToHash(view)}`;
    const shouldReplace = isFirstRun.current;
    isFirstRun.current = false;

    // Already there — e.g. this render was caused by a popstate navigation whose handler already
    // moved location.hash. Pushing again would create a spurious duplicate history entry.
    if (window.location.hash === nextHash) return;

    if (shouldReplace) {
      window.history.replaceState(null, "", nextHash);
    } else {
      window.history.pushState(null, "", nextHash);
    }
  }, [view]);

  useEffect(() => {
    const onPopState = () => setView(parseViewFromHash(window.location.hash));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [setView]);
}
