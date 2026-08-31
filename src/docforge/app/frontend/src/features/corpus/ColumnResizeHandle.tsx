// ====== Code Summary ======
// The grab strip on a resizable header's right edge — a thin idle divider (`line` token) that
// turns into the forge accent while actively dragged, since a live resize is the one thing being
// worked on that header. Double-click auto-fits the column instead of resizing it.

import type { Header } from "@tanstack/react-table";
import { useState } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { theme } from "../../theme";

interface ColumnResizeHandleProps {
  header: Header<DocumentGridRow, unknown>;
  onAutoFit: () => void;
}

export function ColumnResizeHandle({ header, onAutoFit }: ColumnResizeHandleProps) {
  const [hover, setHover] = useState(false);
  const isResizing = header.column.getIsResizing();
  const active = isResizing || hover;

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      title="Drag to resize · double-click to auto-fit"
      // `data-resize-handle` is how the ancestor `<th>`'s dragstart handler recognizes — and
      // cancels — a reorder drag that actually originated here (see TableHeaderCell); `draggable
      // ={false}` alone isn't a reliable enough guard against a draggable ancestor.
      data-resize-handle
      draggable={false}
      onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); header.getResizeHandler()(e); }}
      onTouchStart={(e) => { e.stopPropagation(); header.getResizeHandler()(e); }}
      onDoubleClick={(e) => { e.stopPropagation(); onAutoFit(); }}
      onClick={(e) => e.stopPropagation()}
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
