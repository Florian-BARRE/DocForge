// ====== Code Summary ======
// Guards the actual root cause of the "way too zoomed, illegible" bug: `computeTargetWidthPx` must
// never let an unusually tall page (a whole text-heavy document rendered as one long page) collapse
// to a near-zero width just because its aspect ratio is extreme — the width FLOOR relative to the
// column is what fixes that. Also pins the fit-width baseline and zoom-step scaling.

import { describe, expect, it } from "vitest";
import { computeTargetWidthPx, DEFAULT_PAGE_ZOOM, scaleForStep, zoomPercentLabel } from "./pageZoom";

describe("computeTargetWidthPx", () => {
  it("fit-width at 100% returns exactly the column width", () => {
    const width = computeTargetWidthPx({ preset: "fit-width", step: 0 }, 800, 1000, 600);
    expect(width).toBe(600);
  });

  it("fit-page on a normal portrait page stays within the column width", () => {
    const width = computeTargetWidthPx(DEFAULT_PAGE_ZOOM, 800, 1000, 600);
    expect(width).toBeLessThanOrEqual(600);
    expect(width).toBeGreaterThan(0);
  });

  it("fit-page on a PATHOLOGICALLY TALL page (whole doc as one page) never collapses below the width floor", () => {
    // height:width = 25:1 — the exact class of aspect ratio that made the old `maxHeight: 86vh` +
    // CSS aspect-ratio combo derive a near-zero width.
    const width = computeTargetWidthPx(DEFAULT_PAGE_ZOOM, 800, 20000, 600);
    // Floor is 55% of the column (see FIT_PAGE_MIN_WIDTH_RATIO) — must land at/above it, nowhere
    // near an illegible sliver.
    expect(width).toBeGreaterThanOrEqual(600 * 0.55 - 1);
  });

  it("fit-page on a degenerate/missing intrinsic size does not throw and returns a sane width", () => {
    const width = computeTargetWidthPx(DEFAULT_PAGE_ZOOM, null, null, 600);
    expect(width).toBeGreaterThan(0);
    expect(Number.isFinite(width)).toBe(true);
  });

  it("zoom-in steps scale the width up, zoom-out steps scale it down", () => {
    const base = computeTargetWidthPx({ preset: "fit-width", step: 0 }, 800, 1000, 600);
    const zoomedIn = computeTargetWidthPx({ preset: "fit-width", step: 2 }, 800, 1000, 600);
    const zoomedOut = computeTargetWidthPx({ preset: "fit-width", step: -2 }, 800, 1000, 600);
    expect(zoomedIn).toBeGreaterThan(base);
    expect(zoomedOut).toBeLessThan(base);
  });

  it("clamps to the absolute min/max width even at extreme steps or a tiny/huge column", () => {
    expect(computeTargetWidthPx({ preset: "fit-width", step: -3 }, 800, 1000, 10)).toBeGreaterThanOrEqual(180);
    expect(computeTargetWidthPx({ preset: "fit-width", step: 6 }, 800, 1000, 5000)).toBeLessThanOrEqual(1600);
  });
});

describe("scaleForStep / zoomPercentLabel", () => {
  it("step 0 is 100%", () => {
    expect(scaleForStep(0)).toBe(1);
    expect(zoomPercentLabel(0)).toBe("100%");
  });

  it("each step is a 15% increment", () => {
    expect(scaleForStep(2)).toBeCloseTo(1.3);
    expect(zoomPercentLabel(-2)).toBe("70%");
  });
});
