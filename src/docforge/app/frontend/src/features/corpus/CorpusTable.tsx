// ====== Code Summary ======
// The grid shell — sticky header (sort row) above a virtualized, scrollable body. Only the
// rendered window of rows gets real DOM nodes (TanStack Virtual), so a full page of up to 200 rows
// — or, with metadata columns, many cells each — stays smooth to scroll. Column widths are driven
// by TanStack's own sizing state via a `<colgroup>` (one write per resized column instead of one
// per rendered cell, so dragging stays smooth under virtualization), and header drag-and-drop
// reordering is owned here since it needs `table.setColumnOrder`. The row-actions column
// ("__actions") is deliberately NOT pinned/frozen: an opaque pinned column would float over the
// data columns that have not yet scrolled into view and reads as a stray white panel on the right
// (reported repeatedly) — it is a plain trailing column, reached by scrolling right like any other.
// For the same reason there is no right-edge fade/gradient hint either (removed — it read as the
// same "veil"); the horizontal scrollbar alone communicates that more columns exist. Per-column
// filters live in the separate, toggleable CorpusFilterPanel, not in this table.

import type { Table } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { DocumentGridRow } from "../../api/corpus";
import { theme } from "../../theme";
import { CorpusTableBody } from "./CorpusTableBody";
import { GroupHeaderRow } from "./GroupHeaderRow";
import { lastFlexColumnIndexOf, ROW_HEIGHT, tableWidthOf } from "./tableLayoutModel";
import { TableHeaderCell } from "./TableHeaderCell";
import { isPinnedColumn } from "./types";
import { useCorpusTableLayout } from "./useCorpusTableLayout";

interface CorpusTableProps {
  table: Table<DocumentGridRow>;
  loading: boolean;
}

export function CorpusTable({ table, loading }: CorpusTableProps) {
  const {
    scrollRef, drag, containerWidth, endDrag,
    onHeaderDragStart, onHeaderDragOver, onHeaderDrop, onAutoFit, onResizeStep, onReorderStep,
  } = useCorpusTableLayout(table);
  const rows = table.getRowModel().rows;
  const visibleColumns = table.getVisibleLeafColumns();
  const columnCount = visibleColumns.length;
  const tableWidth = tableWidthOf(containerWidth, table.getTotalSize());

  // The leftover width goes to the last REAL column (not the pinned actions column), see
  // lastFlexColumnIndexOf.
  const lastFlexColumnIndex = lastFlexColumnIndexOf(visibleColumns.map((column) => column.id));
  const definedWidth = visibleColumns.reduce((sum, column) => sum + column.getSize(), 0);
  const leftoverWidth = Math.max(0, tableWidth - definedWidth);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const paddingTop = virtualItems.length ? virtualItems[0].start : 0;
  const paddingBottom = virtualItems.length ? virtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end : 0;

  return (
    <div
      ref={scrollRef}
      style={{
        // `minWidth: 0` overrides the flex item's default `min-width: auto`, which would otherwise
        // let the table's own min-width balloon this wrapper (and the page) past the viewport
        // instead of confining the overflow to this container's own horizontal scrollbar.
        // No background here (each row/header paints its own) — this box is exempt from the
        // list-page width cap (it's an intentionally wide, scrollable grid), but a plain surface
        // fill still shouldn't bleed past the actual rows on a short result set; leaving it
        // transparent lets the warm page-ground show through there instead.
        position: "relative", flex: 1, minHeight: 0, minWidth: 0, overflow: "auto",
        border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
      }}
    >
      <table style={{ borderCollapse: "collapse", tableLayout: "fixed", width: tableWidth }}>
        <colgroup>
          {visibleColumns.map((column, index) => (
            <col
              key={column.id}
              style={{ width: index === lastFlexColumnIndex ? column.getSize() + leftoverWidth : column.getSize() }}
            />
          ))}
        </colgroup>
        <thead style={{ position: "sticky", top: 0, zIndex: 5, background: theme.color.surface }}>
          <GroupHeaderRow columns={visibleColumns} />
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHeaderCell
                  key={header.id}
                  header={header}
                  reorderable={!isPinnedColumn(header.column.id)}
                  isDragSource={drag?.sourceId === header.column.id}
                  dropSide={drag?.overId === header.column.id ? drag.side : null}
                  onDragStart={onHeaderDragStart}
                  onDragOver={onHeaderDragOver}
                  onDrop={onHeaderDrop}
                  onDragEnd={endDrag}
                  onAutoFit={onAutoFit}
                  onResizeStep={onResizeStep}
                  onReorderStep={onReorderStep}
                />
              ))}
            </tr>
          ))}
        </thead>
        <CorpusTableBody
          rows={rows}
          virtualItems={virtualItems}
          paddingTop={paddingTop}
          paddingBottom={paddingBottom}
          columnCount={columnCount}
          loading={loading}
        />
      </table>
    </div>
  );
}
