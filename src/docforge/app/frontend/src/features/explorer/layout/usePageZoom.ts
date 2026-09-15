// ====== Code Summary ======
// Persists the Layout tab's page-zoom choice (preset + step) across reloads — ONE shared setting
// for the whole viewer (per-viewer/browser, not per-document or per-row), same best-effort
// localStorage pattern as useSidebarExpanded/useViewMode: wrapped in try/catch since a private-
// browsing quota/security error must never crash the page, the choice just stops persisting.

import { useEffect, useState } from "react";
import {
  DEFAULT_PAGE_ZOOM,
  ZOOM_STEP_MAX,
  ZOOM_STEP_MIN,
  type PageZoomPreset,
  type PageZoomState,
} from "./pageZoom";

const STORAGE_KEY = "docforge_layout_page_zoom";

function isPageZoomState(value: unknown): value is PageZoomState {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (v.preset === "fit-width" || v.preset === "fit-page") && typeof v.step === "number";
}

function readPersisted(): PageZoomState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return DEFAULT_PAGE_ZOOM;
    const parsed: unknown = JSON.parse(raw);
    return isPageZoomState(parsed) ? parsed : DEFAULT_PAGE_ZOOM;
  } catch {
    return DEFAULT_PAGE_ZOOM;
  }
}

export interface PageZoomControls {
  zoom: PageZoomState;
  setPreset: (preset: PageZoomPreset) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  canZoomIn: boolean;
  canZoomOut: boolean;
}

export function usePageZoom(): PageZoomControls {
  const [zoom, setZoom] = useState<PageZoomState>(readPersisted);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(zoom));
    } catch {
      // Unavailable storage — the choice just stops persisting across reloads, never a hard failure.
    }
  }, [zoom]);

  return {
    zoom,
    setPreset: (preset) => setZoom((z) => (z.preset === preset ? z : { ...z, preset })),
    zoomIn: () => setZoom((z) => ({ ...z, step: Math.min(ZOOM_STEP_MAX, z.step + 1) })),
    zoomOut: () => setZoom((z) => ({ ...z, step: Math.max(ZOOM_STEP_MIN, z.step - 1) })),
    canZoomIn: zoom.step < ZOOM_STEP_MAX,
    canZoomOut: zoom.step > ZOOM_STEP_MIN,
  };
}
