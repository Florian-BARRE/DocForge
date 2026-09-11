// ====== Code Summary ======
// The row-actions column def — thin wiring around CorpusRowActions (delete + the quick re-ingest
// button placed to its left).

import type { ColumnDef } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../../api/corpus";
import { CorpusRowActions } from "../CorpusRowActions";

interface ActionsColumnArgs {
  onDelete: (documentId: string) => Promise<void>;
  onReingested: () => void;
}

// Visually empty (the row's own buttons already carry the meaning) but still a real accessible
// name for the column, not a blank header a screen reader announces as nothing.
const hiddenHeaderStyle: React.CSSProperties = {
  position: "absolute", width: 1, height: 1, padding: 0, margin: -1,
  overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap", border: 0,
};

export function buildActionsColumn({ onDelete, onReingested }: ActionsColumnArgs): ColumnDef<DocumentGridRow> {
  return {
    id: "__actions",
    header: () => <span style={hiddenHeaderStyle}>Actions</span>,
    enableSorting: false,
    enableResizing: false,
    size: 140,
    cell: ({ row }) => (
      <CorpusRowActions documentId={row.original.id} onDelete={() => onDelete(row.original.id)} onReingested={onReingested} />
    ),
  };
}
