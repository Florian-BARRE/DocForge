// ====== Code Summary ======
// Persists whether the user's sidebar is expanded (the full 240px tree) vs. collapsed (the ~72px
// icon rail). Expanded is the DEFAULT — collapsing is an explicit user toggle, never hover/focus-
// gated (2026-09 IA redesign W1: the old hover-to-preview rail hid global chrome — theme/token/nav —
// behind a transient cursor state). Best-effort localStorage — wrapped in try/catch since a private-
// browsing quota/security error must never crash the shell, it just means the choice won't survive a
// reload. Called from App.tsx (not Sidebar itself): App also needs `expanded` to size its own
// content-reserving spacer's INITIAL width before Sidebar's own effect reports in (a compact-viewport
// expansion stays a non-reflowing overlay — see Sidebar.tsx) — so both must read the exact same
// state, not two independent hook instances.

import { useEffect, useState } from "react";

const STORAGE_KEY = "docforge_sidebar_expanded";

function readPersisted(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === null ? true : raw === "1";
  } catch {
    return true;
  }
}

export interface SidebarExpansion {
  expanded: boolean;
  toggleExpanded: () => void;
}

export function useSidebarExpanded(): SidebarExpansion {
  const [expanded, setExpanded] = useState<boolean>(readPersisted);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, expanded ? "1" : "0");
    } catch {
      // Unavailable storage — the choice just stops persisting across reloads, never a hard failure.
    }
  }, [expanded]);

  return { expanded, toggleExpanded: () => setExpanded((e) => !e) };
}
