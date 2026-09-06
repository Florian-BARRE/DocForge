// ====== Code Summary ======
// Persists whether the user pinned the sidebar open (kept expanded regardless of hover/focus).
// Best-effort localStorage — wrapped in try/catch since a private-browsing quota/security error
// must never crash the shell, it just means the pin won't survive a reload. Called from App.tsx
// (not Sidebar itself): App also needs `pinned` to size its own content-reserving spacer — a
// pinned sidebar REFLOWS the page, an unpinned hover/focus expansion only overlays it — so both
// must read the exact same state, not two independent hook instances.

import { useEffect, useState } from "react";

const STORAGE_KEY = "docforge_sidebar_pinned";

function readPersisted(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export interface SidebarPin {
  pinned: boolean;
  togglePinned: () => void;
}

export function useSidebarPin(): SidebarPin {
  const [pinned, setPinned] = useState<boolean>(readPersisted);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, pinned ? "1" : "0");
    } catch {
      // Unavailable storage — the pin just stops persisting across reloads, never a hard failure.
    }
  }, [pinned]);

  return { pinned, togglePinned: () => setPinned((p) => !p) };
}
