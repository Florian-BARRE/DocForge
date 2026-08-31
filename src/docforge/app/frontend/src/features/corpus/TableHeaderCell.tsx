// ====== Code Summary ======
// One column header — its label plus a click-to-sort toggle (asc → desc → none), driven by
// TanStack's own sorting state (the grid runs `manualSorting`, so this only flips local UI state;
// CorpusPage turns it into the one `DocumentSort` the API actually understands).

import { flexRender, type Header } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../api/corpus";
import { theme } from "../../theme";

export function TableHeaderCell({ header }: { header: Header<DocumentGridRow, unknown> }) {
  const sorted = header.column.getIsSorted();
  const canSort = header.column.getCanSort();

  return (
    <th
      style={{
        textAlign: header.column.columnDef.meta?.align === "right" ? "right" : "left",
        padding: `${theme.space.s}px ${theme.space.m}px`, borderBottom: `1px solid ${theme.color.lineStrong}`,
        fontSize: theme.font.size.xs, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em",
        color: theme.color.dim, whiteSpace: "nowrap",
      }}
    >
      {!header.isPlaceholder && (
        <button
          type="button"
          onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
          disabled={!canSort}
          style={{
            background: "none", border: "none", padding: 0, display: "inline-flex", alignItems: "center", gap: 4,
            cursor: canSort ? "pointer" : "default", color: sorted ? theme.color.accent : theme.color.dim,
            font: "inherit", textTransform: "inherit", letterSpacing: "inherit",
          }}
        >
          {flexRender(header.column.columnDef.header, header.getContext())}
          {canSort && <span aria-hidden>{sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : ""}</span>}
        </button>
      )}
    </th>
  );
}
