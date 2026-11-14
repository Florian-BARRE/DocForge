// ====== Code Summary ======
// Pure helpers of the Layout page scrubber (PageScrubber / usePageScrubber): find the scroll container,
// map pointer / scroll positions to a page index, and place a notch along the rail. No React, no
// ownership of state — the DOM reads (rects, ids) are passed in or done by the caller's hook.

export interface PageScrubEntry {
  id: string;
  label: string;
}

/** Nearest scrollable ancestor of an element (the Layout tab's scroll container). */
export function findScroller(from: HTMLElement | null): HTMLElement | null {
  let el = from ?? null;
  while (el) {
    const oy = getComputedStyle(el).overflowY;
    if ((oy === "auto" || oy === "scroll") && el.scrollHeight > el.clientHeight + 4) return el;
    el = el.parentElement;
  }
  return null;
}

/** Position of notch `i` of `n` along the rail, in percent (0 for a single entry). */
export function notchPercent(i: number, n: number): number {
  return n === 1 ? 0 : (i / (n - 1)) * 100;
}

/** Index of the page the scroll position is "on": the last offset at or above `threshold`. */
export function activeIndexAt(offsets: number[], threshold: number): number {
  let current = 0;
  for (const offset of offsets) {
    if (offset <= threshold) current += 1;
    else break;
  }
  return Math.max(0, current - 1);
}

/** Nearest notch under a pointer at `clientY`, for a track at `trackTop` with `trackHeight`. */
export function snapIndexAt(clientY: number, trackTop: number, trackHeight: number, count: number): number {
  const frac = Math.max(0, Math.min(1, (clientY - trackTop) / trackHeight));
  return Math.round(frac * (count - 1));
}

/** The `scrollTop` that brings a target (viewport-relative `targetTop`) just under the scroller's top. */
export function scrollTopForTarget(scrollTop: number, targetTop: number, scrollerTop: number): number {
  return scrollTop + (targetTop - scrollerTop) - 24;
}
