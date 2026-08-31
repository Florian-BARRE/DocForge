// ====== Code Summary ======
// The row-selection checkbox column — header checkbox reflects/toggles "every row currently
// rendered" (works for both selection modes via `UseSelectionResult`), cell checkbox toggles one
// row. Reads the visible row set from `table.getRowModel()` rather than a prop, so it never goes
// stale across a page change.

import type { ColumnDef } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../../api/corpus";
import type { UseSelectionResult } from "../useSelection";

export function buildSelectColumn(selection: UseSelectionResult): ColumnDef<DocumentGridRow> {
  return {
    id: "__select",
    size: 34,
    enableSorting: false,
    header: ({ table }) => {
      const pageIds = table.getRowModel().rows.map((r) => r.original.id);
      return (
        <input
          type="checkbox"
          aria-label="Select all rows on this page"
          checked={selection.allOnPageSelected(pageIds)}
          onChange={() => selection.toggleAllOnPage(pageIds)}
        />
      );
    },
    cell: ({ row }) => (
      <input
        type="checkbox"
        aria-label={`Select ${row.original.filename}`}
        checked={selection.isSelected(row.original.id)}
        onChange={() => selection.toggleRow(row.original.id)}
      />
    ),
  };
}
