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
  const [activeIndex, setActiveIndex] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [hovered, setHovered] = useState(false);

  const scrollToIndex = useCallback((index: number) => {
    const scroller = scrollerRef.current;
    const target = document.getElementById(entries[index]?.id ?? "");
    if (!scroller || !target) return;
    const top = scroller.scrollTop + (target.getBoundingClientRect().top - scroller.getBoundingClientRect().top) - 24;
    scroller.scrollTo({ top, behavior: draggingRef.current ? "auto" : "smooth" });
  }, [entries]);

  // Find the scroll container from the FIRST page anchor (the rail itself is portaled to <body>, so
  // walking its own parents wouldn't reach the Layout scroll area), and track the top page on scroll.
  useEffect(() => {
    const scroller = findScroller(document.getElementById(entries[0]?.id ?? ""));
    scrollerRef.current = scroller;
    if (!scroller) return;
    const onScroll = () => {
      if (draggingRef.current) return;
      const sTop = scroller.getBoundingClientRect().top;
      let current = 0;
      entries.forEach((entry, i) => {
        const el = document.getElementById(entry.id);
        if (el && el.getBoundingClientRect().top - sTop <= 80) current = i;
      });
      setActiveIndex(current);
    };
    scroller.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => scroller.removeEventListener("scroll", onScroll);
  }, [entries]);

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
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
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
        style={{ position: "relative", width: hovered || dragging ? 64 : 22, transition: "width .12s ease", cursor: "pointer" }}
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
