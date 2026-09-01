// ====== Code Summary ======
// The grab strip on a resizable header's right edge — a thin idle divider (`line` token) that
// turns into the forge accent while actively dragged, since a live resize is the one thing being
// worked on that header. Double-click auto-fits the column instead of resizing it. Also focusable
// and keyboard-operable: Left/Right resize in 10px steps, Home/End jump to the column's min/max —
// mirrors the mouse-drag behaviour without changing it (`onResizeStep` is a separate code path
// that reuses TanStack's own `setColumnSizing`, see CorpusTable).
// `role="separator"` with `aria-orientation`/`aria-valuenow` is the ARIA-sanctioned pattern for a
// focusable, adjustable divider (a resize handle has no dedicated APG pattern of its own).

import type { Header } from "@tanstack/react-table";
import { useState, type KeyboardEvent } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { theme } from "../../theme";

const KEYBOARD_STEP_PX = 10;

interface ColumnResizeHandleProps {
  header: Header<DocumentGridRow, unknown>;
  /** The column's header text — feeds the handle's accessible name. */
  label: string;
  onAutoFit: () => void;
  onResizeStep: (nextSize: number) => void;
}

export function ColumnResizeHandle({ header, label, onAutoFit, onResizeStep }: ColumnResizeHandleProps) {
  const [hover, setHover] = useState(false);
  const isResizing = header.column.getIsResizing();
  const active = isResizing || hover;
  const size = header.getSize();
  const minSize = header.column.columnDef.minSize ?? 0;
  const maxSize = header.column.columnDef.maxSize ?? Number.MAX_SAFE_INTEGER;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        onResizeStep(Math.max(minSize, size - KEYBOARD_STEP_PX));
        break;
      case "ArrowRight":
        e.preventDefault();
        onResizeStep(Math.min(maxSize, size + KEYBOARD_STEP_PX));
        break;
      case "Home":
        e.preventDefault();
        onResizeStep(minSize);
        break;
      case "End":
        e.preventDefault();
        if (maxSize < Number.MAX_SAFE_INTEGER) onResizeStep(maxSize);
        break;
      case "Enter":
        e.preventDefault();
        onAutoFit();
        break;
    }
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label} column`}
      aria-valuenow={Math.round(size)}
      aria-valuemin={minSize}
      aria-valuemax={maxSize < Number.MAX_SAFE_INTEGER ? maxSize : undefined}
      tabIndex={0}
      title="Drag to resize · double-click to auto-fit · focus + arrow keys to resize"
      // `data-resize-handle` is how the ancestor `<th>`'s dragstart handler recognizes — and
      // cancels — a reorder drag that actually originated here (see TableHeaderCell); `draggable
      // ={false}` alone isn't a reliable enough guard against a draggable ancestor.
      data-resize-handle
      draggable={false}
      onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); header.getResizeHandler()(e); }}
      onTouchStart={(e) => { e.stopPropagation(); header.getResizeHandler()(e); }}
      onDoubleClick={(e) => { e.stopPropagation(); onAutoFit(); }}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        // Kept fully inside this header's own box (no straddling the column border) — a strip
        // that overlapped the neighbouring `<th>` would lose the browser's hit-test to that
        // sibling cell, silently swallowing the mousedown before TanStack's handler ever saw it.
        position: "absolute", top: 0, right: 0, height: "100%", width: 8,
        cursor: "col-resize", touchAction: "none", userSelect: "none",
        display: "flex", justifyContent: "flex-end", zIndex: 2,
      }}
    >
      <span
        style={{
          width: active ? 2 : 1, height: "100%",
          background: isResizing ? theme.color.accent : active ? theme.color.accentLine : theme.color.line,
          transition: isResizing ? "none" : "background .12s ease, width .12s ease",
        }}
      />
    </div>
  );
}
