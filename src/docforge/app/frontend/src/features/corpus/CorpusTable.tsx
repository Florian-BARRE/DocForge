// ====== Code Summary ======
// The grid shell — sticky header (sort row + filter row) above a virtualized, scrollable body.
// Only the rendered window of rows gets real DOM nodes (TanStack Virtual), so a full page of up
// to 200 rows — or, with metadata columns, many cells each — stays smooth to scroll. Column
// widths are driven by TanStack's own sizing state via a `<colgroup>` (one write per resized
// column instead of one per rendered cell, so dragging stays smooth under virtualization), and
// header drag-and-drop reordering is owned here since it needs `table.setColumnOrder`.

import { flexRender, type Table } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef, useState, type DragEvent } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";
import { autoFitColumnWidth } from "./columnAutoFit";
import { ColumnFilterCell } from "./ColumnFilterCell";
import { ScrollEdgeFade } from "./ScrollEdgeFade";
import { TableHeaderCell, type DropSide } from "./TableHeaderCell";
import { isPinnedColumn, type ColumnFilterValue, type ColumnFiltersState } from "./types";
import { useTrailingScrollFade } from "./useTrailingScrollFade";

interface CorpusTableProps {
  table: Table<DocumentGridRow>;
  loading: boolean;
  columnFilters: ColumnFiltersState;
  onColumnFilterChange: (columnId: string, value: ColumnFilterValue) => void;
}

const ROW_HEIGHT = 40;
// `tableLayout: fixed` + an explicit table width needs a floor to compress against — without one
// the browser happily squeezes every column to near-zero at narrow viewports instead of ever
// overflowing the `overflow-x: auto` wrapper (scrollWidth stayed === clientWidth, so it never
// scrolled sideways). Shipped in 0.8.2 — keep honoring it against the live TanStack column sizes.
const MIN_TABLE_WIDTH = 1100;

interface DragState {
  sourceId: string;
  overId: string | null;
  side: DropSide;
}

export function CorpusTable({ table, loading, columnFilters, onColumnFilterChange }: CorpusTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const rows = table.getRowModel().rows;
  const columnCount = table.getVisibleLeafColumns().length;
  const tableWidth = Math.max(MIN_TABLE_WIDTH, table.getTotalSize());

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const paddingTop = virtualItems.length ? virtualItems[0].start : 0;
  const paddingBottom = virtualItems.length ? virtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end : 0;
  const canScrollRight = useTrailingScrollFade(scrollRef, [tableWidth, columnCount, rows.length]);

  const onHeaderDragStart = (columnId: string) => setDrag({ sourceId: columnId, overId: null, side: "after" });

  const onHeaderDragOver = (e: DragEvent<HTMLTableCellElement>, columnId: string) => {
    if (!drag || drag.sourceId === columnId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const side: DropSide = e.clientX - rect.left < rect.width / 2 ? "before" : "after";
    setDrag((prev) => (prev ? { ...prev, overId: columnId, side } : prev));
  };

  const onHeaderDrop = () => {
    if (drag?.overId && drag.overId !== drag.sourceId) {
      const current = table.getState().columnOrder;
      const without = current.filter((id) => id !== drag.sourceId);
      const targetIndex = without.indexOf(drag.overId);
      const insertAt = drag.side === "before" ? targetIndex : targetIndex + 1;
      table.setColumnOrder([...without.slice(0, insertAt), drag.sourceId, ...without.slice(insertAt)]);
    }
    setDrag(null);
  };

  const onAutoFit = (columnId: string) => {
    if (!scrollRef.current) return;
    const column = table.getColumn(columnId);
    if (!column) return;
    const minSize = column.columnDef.minSize ?? 60;
    const fitted = autoFitColumnWidth(scrollRef.current, columnId, minSize);
    table.setColumnSizing((prev) => ({ ...prev, [columnId]: fitted }));
  };

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
          {table.getVisibleLeafColumns().map((column) => (
            <col key={column.id} style={{ width: column.getSize() }} />
          ))}
        </colgroup>
        <thead style={{ position: "sticky", top: 0, zIndex: 5, background: theme.color.surface }}>
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
                  onDragEnd={() => setDrag(null)}
                  onAutoFit={onAutoFit}
                />
              ))}
            </tr>
          ))}
          <tr>
            {table.getVisibleLeafColumns().map((column) => {
              const filterKind = column.columnDef.meta?.filterKind;
              return (
                <th
                  key={column.id}
                  style={{ padding: "4px 8px", borderBottom: `1px solid ${theme.color.line}`, background: theme.color.surface2 }}
                >
                  {filterKind && (
                    <ColumnFilterCell
                      columnId={column.id}
                      filterKind={filterKind}
                      enumOptions={column.columnDef.meta?.enumOptions}
                      value={columnFilters[column.id]}
                      onChange={onColumnFilterChange}
                    />
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading && rows.length === 0 && (
            <tr style={{ background: theme.color.surface }}><td colSpan={columnCount}><LoadingState label="loading documents…" /></td></tr>
          )}
          {!loading && rows.length === 0 && (
            <tr style={{ background: theme.color.surface }}>
              <td colSpan={columnCount} style={{ textAlign: "center", padding: theme.space.xxl, color: theme.color.dim, fontSize: theme.font.size.l }}>
                No documents match the current filter.
              </td>
            </tr>
          )}
          {rows.length > 0 && paddingTop > 0 && <tr aria-hidden style={{ height: paddingTop }} />}
          {virtualItems.map((virtualRow) => {
            const row = rows[virtualRow.index];
            return (
              <tr
                key={row.id}
                className="df-row-hover"
                style={{ borderBottom: `1px solid ${theme.color.line}`, opacity: row.original.enabled ? 1 : 0.6 }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    data-col-id={cell.column.id}
                    style={{
                      padding: "6px 8px", fontSize: theme.font.size.s, color: theme.color.text,
                      overflow: "hidden",
                      textAlign: cell.column.columnDef.meta?.align === "right" ? "right" : "left",
                      ...(cell.column.columnDef.meta?.mono ? { fontFamily: theme.font.mono, color: theme.color.dim, fontSize: theme.font.size.xs } : {}),
                    }}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            );
          })}
          {rows.length > 0 && paddingBottom > 0 && <tr aria-hidden style={{ height: paddingBottom }} />}
        </tbody>
      </table>
      <ScrollEdgeFade visible={canScrollRight} />
    </div>
  );
}
