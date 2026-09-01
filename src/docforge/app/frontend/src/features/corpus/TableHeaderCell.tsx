// ====== Code Summary ======
// One column header — its label plus a click-to-sort toggle (asc → desc → none), driven by
// TanStack's own sorting state (the grid runs `manualSorting`, so this only flips local UI state;
// CorpusPage turns it into the one `DocumentSort` the API actually understands). Reorderable
// headers are also HTML5 drag sources/targets (native drag only starts once the pointer actually
// moves, so a plain click still reaches the sort button underneath) and carry a resize handle on
// their trailing edge.

import { flexRender, type Header } from "@tanstack/react-table";
import type { DragEvent, KeyboardEvent } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { theme } from "../../theme";
import { ColumnResizeHandle } from "./ColumnResizeHandle";

export type DropSide = "before" | "after";

interface TableHeaderCellProps {
  header: Header<DocumentGridRow, unknown>;
  reorderable: boolean;
  isDragSource: boolean;
  dropSide: DropSide | null;
  onDragStart: (columnId: string) => void;
  onDragOver: (e: DragEvent<HTMLTableCellElement>, columnId: string) => void;
  onDrop: () => void;
  onDragEnd: () => void;
  onAutoFit: (columnId: string) => void;
  onResizeStep: (columnId: string, nextSize: number) => void;
  /** Keyboard path for drag-reorder — Alt+Left/Right on the header's own sort button (mouse drag is unchanged). */
  onReorderStep: (columnId: string, direction: -1 | 1) => void;
}

export function TableHeaderCell({
  header, reorderable, isDragSource, dropSide, onDragStart, onDragOver, onDrop, onDragEnd, onAutoFit, onResizeStep, onReorderStep,
}: TableHeaderCellProps) {
  const sorted = header.column.getIsSorted();
  const canSort = header.column.getCanSort();
  const canResize = header.column.getCanResize();
  const label = typeof header.column.columnDef.header === "string" ? header.column.columnDef.header : header.column.id;

  const onSortButtonKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (!reorderable || !e.altKey) return;
    if (e.key === "ArrowLeft") { e.preventDefault(); onReorderStep(header.column.id, -1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); onReorderStep(header.column.id, 1); }
  };

  return (
    <th
      data-col-id={header.column.id}
      draggable={reorderable}
      onDragStart={(e) => {
        // The resize handle sits inside this same draggable `<th>` — `draggable={false}` on it
        // isn't enough on its own (Chromium can still resolve the drag source to the nearest
        // draggable ancestor once the pointer moves), so cancel the reorder drag outright when it
        // actually originated on the handle. `dragstart` is spec-guaranteed cancelable, unlike the
        // mousedown-level heuristic.
        if ((e.target as HTMLElement).closest('[data-resize-handle]')) { e.preventDefault(); return; }
        e.dataTransfer.effectAllowed = "move";
        onDragStart(header.column.id);
      }}
      onDragOver={(e) => { if (reorderable) { e.preventDefault(); onDragOver(e, header.column.id); } }}
      onDrop={(e) => { if (reorderable) { e.preventDefault(); onDrop(); } }}
      onDragEnd={onDragEnd}
      title={reorderable ? "Drag to reorder · focus the label + Alt+←/→ to reorder via keyboard" : undefined}
      style={{
        position: "relative",
        textAlign: header.column.columnDef.meta?.align === "right" ? "right" : "left",
        padding: `${theme.space.s}px ${theme.space.m}px`, borderBottom: `1px solid ${theme.color.lineStrong}`,
        fontSize: theme.font.size.xs, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em",
        color: theme.color.dim, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        cursor: reorderable ? "grab" : undefined,
        opacity: isDragSource ? 0.4 : 1,
        boxShadow: dropSide === "before"
          ? `inset 2px 0 0 ${theme.color.accent}`
          : dropSide === "after"
            ? `inset -2px 0 0 ${theme.color.accent}`
            : "none",
      }}
    >
      {!header.isPlaceholder && (canSort ? (
        <button
          type="button"
          onClick={header.column.getToggleSortingHandler()}
          onKeyDown={onSortButtonKeyDown}
          aria-keyshortcuts={reorderable ? "Alt+ArrowLeft Alt+ArrowRight" : undefined}
          style={{
            background: "none", border: "none", padding: 0, display: "inline-flex", alignItems: "center", gap: 4,
            cursor: "pointer", color: sorted ? theme.color.accent : theme.color.dim,
            font: "inherit", textTransform: "inherit", letterSpacing: "inherit",
          }}
        >
          {flexRender(header.column.columnDef.header, header.getContext())}
          <span aria-hidden>{sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : ""}</span>
        </button>
      ) : (
        // A plain wrapper, not a `<button disabled>`: a disabled ancestor form control blocks
        // event bubbling to descendants in Chromium, which silently ate clicks on the select-all
        // checkbox nested inside an unsortable header (see BUG #1 in QA batch 2026-08-31).
        <div style={{ display: "inline-flex", alignItems: "center", gap: 4, color: theme.color.dim }}>
          {flexRender(header.column.columnDef.header, header.getContext())}
        </div>
      ))}
      {canResize && (
        <ColumnResizeHandle
          header={header}
          label={label}
          onAutoFit={() => onAutoFit(header.column.id)}
          onResizeStep={(nextSize) => onResizeStep(header.column.id, nextSize)}
        />
      )}
    </th>
  );
}
