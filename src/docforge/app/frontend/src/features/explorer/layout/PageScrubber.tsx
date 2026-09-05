// ====== Code Summary ======
// A vertical page scrubber pinned to the right of the Layout tab — a scrollbar-like rail with one
// precise notch per page group. The current page is highlighted as you scroll; clicking a notch jumps
// to that page, and DRAGGING the thumb snaps magnetically page-by-page (the nearest notch under the
// pointer wins) for fast up/down navigation of long documents. It drives the Layout's own scroll
// container (found by walking up the DOM), so it works inside the app's nested scroll area.

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { theme } from "../../../theme";

export interface PageScrubEntry {
  id: string;
  label: string;
}

interface PageScrubberProps {
  entries: PageScrubEntry[];
}

/** Nearest scrollable ancestor of an element (the Layout tab's scroll container). */
function findScroller(from: HTMLElement | null): HTMLElement | null {
  let el = from ?? null;
  while (el) {
    const oy = getComputedStyle(el).overflowY;
    if ((oy === "auto" || oy === "scroll") && el.scrollHeight > el.clientHeight + 4) return el;
    el = el.parentElement;
  }
  return null;
}

export function PageScrubber({ entries }: PageScrubberProps) {
  const rootRef = useRef<HTMLDivElement>(null);
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
    const top = scroller.scrollTop + (target.getBoundingClientRect().top - scroller.getBoundingClientRect().top) - 24;
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
    const threshold = scroller.scrollTop + 80;
    let current = 0;
    for (const offset of offsetsRef.current) {
      if (offset <= threshold) current += 1;
      else break;
    }
    setActiveIndex(Math.max(0, current - 1));
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
    const frac = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    const index = Math.round(frac * (entries.length - 1));
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

  if (entries.length <= 1) return null;

  const n = entries.length;
  const pct = (i: number) => (n === 1 ? 0 : (i / (n - 1)) * 100);

  // Portaled to <body> so position:fixed is viewport-relative (the Layout's .df-rise ancestor has a
  // transform, which would otherwise trap a fixed element inside the content column).
  return createPortal(
    <div
      ref={rootRef}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-label="Page navigator"
      style={{
        position: "fixed",
        right: 10,
        top: "50%",
        transform: "translateY(-50%)",
        height: "min(70vh, 620px)",
        display: "flex",
        alignItems: "stretch",
        zIndex: 20,
        userSelect: "none",
      }}
    >
      <div
        ref={trackRef}
        onPointerDown={(e) => {
          draggingRef.current = true;
          setDragging(true);
          snapToPointer(e.clientY);
        }}
        style={{
          position: "relative",
          width: hovered || dragging ? 64 : 22,
          transition: "width .12s ease",
          cursor: "pointer",
          // Without this, a touch drag on the track is hijacked by the browser as a page-pan/scroll
          // gesture (firing "pointercancel" before our pointermove handler ever sees the movement).
          touchAction: "none",
        }}
      >
        {/* The rail line */}
        <div
          style={{
            position: "absolute",
            right: 9,
            top: 0,
            bottom: 0,
            width: 2,
            borderRadius: theme.radius.pill,
            background: theme.color.line,
          }}
        />
        {/* Progress fill from top to the active notch */}
        <div
          style={{
            position: "absolute",
            right: 9,
            top: 0,
            height: `${pct(activeIndex)}%`,
            width: 2,
            borderRadius: theme.radius.pill,
            background: theme.color.accent,
            transition: dragging ? "none" : "height .12s ease",
          }}
        />
        {entries.map((entry, i) => {
          const active = i === activeIndex;
          const show = hovered || dragging || active;
          return (
            <button
              key={entry.id}
              type="button"
              title={`Page ${entry.label}`}
              onClick={(e) => {
                e.stopPropagation();
                setActiveIndex(i);
                scrollToIndex(i);
              }}
              style={{
                position: "absolute",
                right: 0,
                top: `${pct(i)}%`,
                transform: "translateY(-50%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-end",
                gap: 5,
                width: "100%",
                background: "none",
                border: "none",
                padding: 0,
                cursor: "pointer",
              }}
            >
              <span
                style={{
                  fontFamily: theme.font.mono,
                  fontSize: theme.font.size.xs,
                  lineHeight: 1,
                  color: active ? theme.color.onAccent : theme.color.dim,
                  background: active ? theme.color.accent : theme.color.surface,
                  border: `1px solid ${active ? theme.color.accent : theme.color.line}`,
                  borderRadius: theme.radius.pill,
                  padding: "1px 6px",
                  opacity: show ? 1 : 0,
                  transform: show ? "translateX(0)" : "translateX(8px)",
                  transition: "opacity .12s ease, transform .12s ease",
                  pointerEvents: "none",
                  whiteSpace: "nowrap",
                }}
              >
                {entry.label}
              </span>
              {/* The notch */}
              <span
                style={{
                  flex: "none",
                  width: active ? 14 : 8,
                  height: active ? 3 : 2,
                  borderRadius: theme.radius.pill,
                  background: active ? theme.color.accent : theme.color.lineStrong,
                  marginRight: 3,
                  transition: "width .12s ease, background .12s ease",
                }}
              />
            </button>
          );
        })}
      </div>
    </div>,
    document.body,
  );
}
