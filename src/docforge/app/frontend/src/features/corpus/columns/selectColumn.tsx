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
    enableResizing: false,
    header: ({ table }) => {
      const pageIds = table.getRowModel().rows.map((r) => r.original.id);
      const allSelected = selection.allOnPageSelected(pageIds);
      // Partial page selection reads as an indeterminate (dash) box, so a fully-checked header
      // unambiguously means "the whole page", not "some rows".
      const partial = !allSelected && pageIds.some((id) => selection.isSelected(id));
      return (
        <input
          type="checkbox"
          ref={(el) => { if (el) el.indeterminate = partial; }}
          aria-label="Select all rows on this page"
          checked={allSelected}
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
