// ====== Code Summary ======
// State + effects of the Layout page scrubber: which page is active (follows the Layout's own scroll
// container), drag-to-snap on the rail, and click-to-jump. The view (PageScrubber) only renders what
// this hook returns; the pure position maths live in scrubberModel.ts.

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import {
  activeIndexAt,
  findScroller,
  scrollTopForTarget,
  snapIndexAt,
  type PageScrubEntry,
} from "./scrubberModel";

export interface PageScrubberState {
  trackRef: RefObject<HTMLDivElement | null>;
  activeIndex: number;
  dragging: boolean;
  hovered: boolean;
  setHovered: (hovered: boolean) => void;
  /** Start a drag on the track and snap to the pointer. */
  beginDrag: (clientY: number) => void;
  /** Jump to a page (a notch click). */
  jumpTo: (index: number) => void;
}

export function usePageScrubber(entries: PageScrubEntry[]): PageScrubberState {
  const trackRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLElement | null>(null);
  const draggingRef = useRef(false);
  // Per-entry top offset relative to the scroller's CONTENT (not the viewport) — computed once per
  // layout pass, not read back from the DOM on every scroll tick (that used to be an O(pages)
  // getBoundingClientRect() sweep per event). Only `scrollerTopRef` (one rect read) is checked per
  // tick, and a real recompute only fires when that drifts (the scroller itself moved).
  const offsetsRef = useRef<number[]>([]);
  const scrollerTopRef = useRef(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [hovered, setHovered] = useState(false);

  const scrollToIndex = useCallback((index: number) => {
    const target = document.getElementById(entries[index]?.id ?? "");
    // Re-derived fresh (cheap ancestor walk, only on user interaction) rather than trusting a
    // possibly-stale cached ref — the target's own scroll container may have remounted since bind.
    const scroller = findScroller(target) ?? scrollerRef.current;
    if (!scroller || !target) return;
    scrollerRef.current = scroller;
    const top = scrollTopForTarget(
      scroller.scrollTop,
      target.getBoundingClientRect().top,
      scroller.getBoundingClientRect().top,
    );
    scroller.scrollTo({ top, behavior: draggingRef.current ? "auto" : "smooth" });
  }, [entries]);

  const recomputeOffsets = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const sTop = scroller.getBoundingClientRect().top;
    scrollerTopRef.current = sTop;
    offsetsRef.current = entries.map((entry) => {
      const el = document.getElementById(entry.id);
      return el ? el.getBoundingClientRect().top - sTop + scroller.scrollTop : 0;
    });
  }, [entries]);

  const updateActiveIndex = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    // The scroller's own position can shift (an outer page scroll, a layout change) without firing
    // through our rebind path — a single cheap rect read detects that drift and refreshes the cache.
    if (Math.abs(scroller.getBoundingClientRect().top - scrollerTopRef.current) > 1) recomputeOffsets();
    setActiveIndex(activeIndexAt(offsetsRef.current, scroller.scrollTop + 80));
  }, [recomputeOffsets]);

  // Find the scroll container from the FIRST page anchor (the rail itself is portaled to <body>, so
  // walking its own parents wouldn't reach the Layout scroll area). Bound at the WINDOW level with
  // `capture: true` so a scroll firing on any nested scrollable ancestor is still observed — the
  // rail no longer depends on a single element reference staying valid; a container remount (tab
  // switch, re-render) is simply re-resolved from the anchor the next time a scroll/resize fires.
  useEffect(() => {
    const rebind = () => {
      const anchor = document.getElementById(entries[0]?.id ?? "");
      const next = findScroller(anchor);
      if (next !== scrollerRef.current) {
        scrollerRef.current = next;
        recomputeOffsets();
      }
    };

    const onScroll = (e: Event) => {
      if (draggingRef.current) return;
      if (e.target !== scrollerRef.current) {
        rebind();
        if (e.target !== scrollerRef.current) return; // an unrelated scroll elsewhere on the page
      }
      updateActiveIndex();
    };
    const onResize = () => {
      rebind();
      updateActiveIndex();
    };

    rebind();
    updateActiveIndex();
    window.addEventListener("scroll", onScroll, { capture: true, passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [entries, recomputeOffsets, updateActiveIndex]);

  // Drag → snap to the nearest notch under the pointer (magnetic, page-by-page).
  const snapToPointer = useCallback((clientY: number) => {
    const track = trackRef.current;
    if (!track || entries.length < 2) return;
    const rect = track.getBoundingClientRect();
    const index = snapIndexAt(clientY, rect.top, rect.height, entries.length);
    setActiveIndex((prev) => {
      if (index !== prev) scrollToIndex(index);
      return index;
    });
  }, [entries, scrollToIndex]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: PointerEvent) => snapToPointer(e.clientY);
    const onUp = () => {
      draggingRef.current = false;
      setDragging(false);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    // A touch drag that strays gets "pointercancel"-ed by the browser (e.g. it decides the gesture
    // is a page pan) rather than "pointerup" — without this the rail would stay stuck in drag mode.
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [dragging, snapToPointer]);

  const beginDrag = useCallback((clientY: number) => {
    draggingRef.current = true;
    setDragging(true);
    snapToPointer(clientY);
  }, [snapToPointer]);

  const jumpTo = useCallback((index: number) => {
    setActiveIndex(index);
    scrollToIndex(index);
  }, [scrollToIndex]);

  return { trackRef, activeIndex, dragging, hovered, setHovered, beginDrag, jumpTo };
}
