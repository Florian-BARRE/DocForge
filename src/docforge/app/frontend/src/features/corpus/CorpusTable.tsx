// ====== Code Summary ======
// The grid shell — sticky header (sort row + filter row) above a virtualized, scrollable body.
// Only the rendered window of rows gets real DOM nodes (TanStack Virtual), so a full page of up
// to 200 rows — or, with metadata columns, many cells each — stays smooth to scroll.

import { flexRender, type Table } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";
import { ColumnFilterCell } from "./ColumnFilterCell";
import { TableHeaderCell } from "./TableHeaderCell";
import type { ColumnFilterValue, ColumnFiltersState } from "./types";

interface CorpusTableProps {
  table: Table<DocumentGridRow>;
  loading: boolean;
  columnFilters: ColumnFiltersState;
  onColumnFilterChange: (columnId: string, value: ColumnFilterValue) => void;
}

const ROW_HEIGHT = 40;
// `tableLayout: fixed` needs an explicit width to compress against — without a floor the browser
// happily squeezes every column to near-zero at narrow viewports instead of ever overflowing the
// `overflow-x: auto` wrapper (scrollWidth stayed === clientWidth, so it never scrolled sideways).
const MIN_COLUMN_WIDTH = 110;
const MIN_TABLE_WIDTH = 1100;

export function CorpusTable({ table, loading, columnFilters, onColumnFilterChange }: CorpusTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rows = table.getRowModel().rows;
  const columnCount = table.getVisibleLeafColumns().length;

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
        flex: 1, minHeight: 0, minWidth: 0, overflow: "auto",
        background: theme.color.surface, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
      }}
    >
      <table
        style={{
          borderCollapse: "collapse", width: "100%", tableLayout: "fixed",
          minWidth: Math.max(MIN_TABLE_WIDTH, columnCount * MIN_COLUMN_WIDTH),
        }}
      >
        <thead style={{ position: "sticky", top: 0, zIndex: 5, background: theme.color.surface }}>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => <TableHeaderCell key={header.id} header={header} />)}
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
            <tr><td colSpan={columnCount}><LoadingState label="loading documents…" /></td></tr>
          )}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columnCount} style={{ textAlign: "center", padding: theme.space.xxl, color: theme.color.dim, fontSize: theme.font.size.l }}>
                No documents match the current filter.
              </td>
            </tr>
          )}
          {rows.length > 0 && paddingTop > 0 && <tr aria-hidden style={{ height: paddingTop }} />}
          {virtualItems.map((virtualRow) => {
            const row = rows[virtualRow.index];
            return (
              <tr key={row.id} style={{ borderBottom: `1px solid ${theme.color.line}`, opacity: row.original.enabled ? 1 : 0.6 }}>
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
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
    </div>
  );
}
