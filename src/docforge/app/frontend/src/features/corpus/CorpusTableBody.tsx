// ====== Code Summary ======
// The virtualized `<tbody>` of the corpus grid: loading / empty placeholders, the spacer rows that
// stand in for the rows outside the virtual window, and one real `<tr>` per windowed row.

import { flexRender, type Row } from "@tanstack/react-table";
import type { VirtualItem } from "@tanstack/react-virtual";
import type { DocumentGridRow } from "../../api/corpus";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";

interface CorpusTableBodyProps {
  rows: Row<DocumentGridRow>[];
  virtualItems: VirtualItem[];
  paddingTop: number;
  paddingBottom: number;
  columnCount: number;
  loading: boolean;
}

export function CorpusTableBody({ rows, virtualItems, paddingTop, paddingBottom, columnCount, loading }: CorpusTableBodyProps) {
  return (
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
  );
}
