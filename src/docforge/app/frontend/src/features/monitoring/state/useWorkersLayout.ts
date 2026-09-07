// ====== Code Summary ======
// Persists the viewer's chosen worker-card layout (List / a fixed column count / Auto) across
// reloads. Best-effort localStorage — wrapped in try/catch since a private-browsing quota/security
// error must never crash the page, it just means the choice won't survive a reload (same pattern as
// useSidebarPin.ts). Defaults to "auto" (today's `repeat(auto-fill, minmax(320px, 1fr))` behavior)
// when nothing is persisted yet or the stored value is unrecognized.

import { useEffect, useState } from "react";

const STORAGE_KEY = "docforge_workers_layout";

export type WorkersLayout = "list" | "auto" | 2 | 3;

const VALID_LAYOUTS: WorkersLayout[] = ["list", "auto", 2, 3];

function isValidLayout(value: unknown): value is WorkersLayout {
  return VALID_LAYOUTS.includes(value as WorkersLayout);
}

function readPersisted(): WorkersLayout {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return "auto";
    const parsed: unknown = raw === "list" || raw === "auto" ? raw : Number(raw);
    return isValidLayout(parsed) ? parsed : "auto";
  } catch {
    return "auto";
  }
}

/** The CSS `grid-template-columns` value for a given layout choice. */
export function gridTemplateColumnsFor(layout: WorkersLayout): string {
  if (layout === "list") return "1fr";
  if (layout === "auto") return "repeat(auto-fill, minmax(320px, 1fr))";
  return `repeat(${layout}, minmax(0, 1fr))`;
}

export interface WorkersLayoutState {
  layout: WorkersLayout;
  setLayout: (layout: WorkersLayout) => void;
}

export function useWorkersLayout(): WorkersLayoutState {
  const [layout, setLayout] = useState<WorkersLayout>(readPersisted);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(layout));
    } catch {
      // Unavailable storage — the choice just stops persisting across reloads, never a hard failure.
    }
  }, [layout]);

  return { layout, setLayout };
}
