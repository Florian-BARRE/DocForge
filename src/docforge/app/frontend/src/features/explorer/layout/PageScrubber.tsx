// ====== Code Summary ======
// A vertical page scrubber pinned to the right of the Layout tab — a scrollbar-like rail with one
// precise notch per page group. The current page is highlighted as you scroll; clicking a notch jumps
// to that page, and DRAGGING the thumb snaps magnetically page-by-page (the nearest notch under the
// pointer wins) for fast up/down navigation of long documents. It drives the Layout's own scroll
// container (found by walking up the DOM), so it works inside the app's nested scroll area.

import { createPortal } from "react-dom";

import { theme } from "../../../theme";
import { notchPercent, type PageScrubEntry } from "./scrubberModel";
import { usePageScrubber } from "./usePageScrubber";

export type { PageScrubEntry };

interface PageScrubberProps {
  entries: PageScrubEntry[];
}

export function PageScrubber({ entries }: PageScrubberProps) {
  const { trackRef, activeIndex, dragging, hovered, setHovered, beginDrag, jumpTo } = usePageScrubber(entries);

  if (entries.length <= 1) return null;

  const n = entries.length;
  const pct = (i: number) => notchPercent(i, n);

  // Portaled to <body> so position:fixed is viewport-relative (the Layout's .df-rise ancestor has a
  // transform, which would otherwise trap a fixed element inside the content column).
  return createPortal(
    <div
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
        onPointerDown={(e) => beginDrag(e.clientY)}
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
                jumpTo(i);
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
