// ====== Code Summary ======
// Pure geometry for the Layout tab's page-zoom control: turns a zoom preset + step into a target
// image WIDTH in pixels — never a height cap. WIDTH-driven sizing is the actual fix for the
// "way too zoomed" bug: the old `maxHeight: 86vh` cap forced the browser to derive the image's
// width from its height via the CSS `aspect-ratio`, which pathologically shrinks an unusually tall
// page (e.g. a whole text-heavy .md rendered as one long page) down to an illegible sliver. Driving
// width directly — with a floor relative to the column — keeps every page comfortably wide
// regardless of its own aspect ratio, and lets the user zoom in further for detail.

export type PageZoomPreset = "fit-width" | "fit-page";

export interface PageZoomState {
  preset: PageZoomPreset;
  /** Integer zoom step, 0 = 100% of the preset's own baseline width. Each step is +/- 15%. */
  step: number;
}

export const DEFAULT_PAGE_ZOOM: PageZoomState = { preset: "fit-page", step: 0 };

export const ZOOM_STEP_MIN = -3;
export const ZOOM_STEP_MAX = 6;
const STEP_RATIO = 0.15;

/** The scale multiplier a zoom step applies on top of the preset's baseline width. */
export function scaleForStep(step: number): number {
  return 1 + step * STEP_RATIO;
}

/** Human-readable zoom percentage for the control's readout. */
export function zoomPercentLabel(step: number): string {
  return `${Math.round(scaleForStep(step) * 100)}%`;
}

// "Fit page" targets a page landing in a comfortable box roughly this tall before any zoom step —
// replaces the old blanket `86vh`. Combined with FIT_PAGE_MIN_WIDTH_RATIO below (a width FLOOR) so
// a pathological aspect ratio never collapses the page to an unreadable sliver — that floor is the
// actual bug fix, `computeTargetWidthPx`'s own tests pin it down.
const FIT_PAGE_TARGET_HEIGHT_PX = 640;
const FIT_PAGE_MIN_WIDTH_RATIO = 0.55;

const ABSOLUTE_MIN_WIDTH_PX = 180;
const ABSOLUTE_MAX_WIDTH_PX = 1600;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * The target image WIDTH (px) for a page, given the current zoom state and the page's own
 * intrinsic size. `columnWidthPx` is the measured available width of the page column (or the full
 * row width once stacked) — the ceiling for "fit" sizing; a zoom step can push the result past it
 * (the caller then scrolls the page horizontally within its own wrapper).
 */
export function computeTargetWidthPx(
  zoom: PageZoomState,
  naturalWidth: number | null,
  naturalHeight: number | null,
  columnWidthPx: number,
): number {
  const scale = scaleForStep(zoom.step);
  const safeColumn = columnWidthPx > 0 ? columnWidthPx : ABSOLUTE_MAX_WIDTH_PX;

  let baseline: number;
  if (zoom.preset === "fit-width") {
    baseline = safeColumn;
  } else {
    // No/degenerate intrinsic size falls back to a plain-portrait-ish ratio rather than skewing
    // the floor logic below with a division by (near) zero.
    const aspect = naturalWidth && naturalHeight && naturalWidth > 0 ? naturalHeight / naturalWidth : 1.3;
    const heightDrivenWidth = FIT_PAGE_TARGET_HEIGHT_PX / aspect;
    const floor = safeColumn * FIT_PAGE_MIN_WIDTH_RATIO;
    baseline = clamp(heightDrivenWidth, floor, safeColumn);
  }

  return Math.round(clamp(baseline * scale, ABSOLUTE_MIN_WIDTH_PX, ABSOLUTE_MAX_WIDTH_PX));
}
