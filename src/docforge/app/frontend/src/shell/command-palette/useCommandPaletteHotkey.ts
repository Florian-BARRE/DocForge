// ====== Code Summary ======
// Global ⌘K / Ctrl+K listener that opens the command palette from anywhere in the app. Attached
// once at the root (App.tsx) via `window`, so it fires regardless of which view is currently
// mounted — the palette itself is a sibling of the routed view, not nested inside it.

import { useEffect } from "react";

export function useCommandPaletteHotkey(onOpen: () => void): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpen]);
}
