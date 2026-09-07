// ====== Code Summary ======
// Persists the viewer's chosen list layout — one-per-row "list", or a card "grid" at a chosen
// column count (a fixed N or "auto", today's `repeat(auto-fill, minmax(<min>px,1fr))` behavior).
// Generalizes the former worker-only `useWorkersLayout` so both the Workers and Collections pages
// share one hook, each under its own localStorage key (so their choices persist independently).
// Best-effort localStorage — wrapped in try/catch since a private-browsing quota/security error must
// never crash the page (same pattern as useSidebarPin.ts). Defaults to grid+auto (today's behaviour)
// when nothing is persisted yet or the stored value is malformed.

import { useEffect, useState } from "react";

export type ViewModeColumns = "auto" | 2 | 3 | 4;

export type ViewMode = { kind: "list" } | { kind: "grid"; columns: ViewModeColumns };

const DEFAULT_MODE: ViewMode = { kind: "grid", columns: "auto" };

const VALID_COLUMNS: ViewModeColumns[] = ["auto", 2, 3, 4];

function isViewMode(value: unknown): value is ViewMode {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (v.kind === "list") return true;
  if (v.kind === "grid") return VALID_COLUMNS.includes(v.columns as ViewModeColumns);
  return false;
}

function readPersisted(storageKey: string): ViewMode {
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw === null) return DEFAULT_MODE;
    const parsed: unknown = JSON.parse(raw);
    return isViewMode(parsed) ? parsed : DEFAULT_MODE;
  } catch {
    return DEFAULT_MODE;
  }
}

/** The CSS `grid-template-columns` value for a given view mode — `minPx` is the per-page card
 *  minimum width used by "auto" (Collections and Workers each keep their own historical minimum). */
export function gridTemplateColumnsFor(mode: ViewMode, minPx: number): string {
  if (mode.kind === "list") return "1fr";
  if (mode.columns === "auto") return `repeat(auto-fill, minmax(${minPx}px, 1fr))`;
  return `repeat(${mode.columns}, minmax(0, 1fr))`;
}

export interface ViewModeState {
  mode: ViewMode;
  setMode: (mode: ViewMode) => void;
}

/** `storageKey` must be distinct per page (e.g. `docforge_view_workers`) so each page's choice
 *  persists independently of the others. */
export function useViewMode(storageKey: string): ViewModeState {
  const [mode, setMode] = useState<ViewMode>(() => readPersisted(storageKey));

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(mode));
    } catch {
      // Unavailable storage — the choice just stops persisting across reloads, never a hard failure.
    }
  }, [storageKey, mode]);

  return { mode, setMode };
}
