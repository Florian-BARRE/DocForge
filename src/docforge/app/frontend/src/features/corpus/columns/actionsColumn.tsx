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

export function buildActionsColumn({ onDelete, onReingested }: ActionsColumnArgs): ColumnDef<DocumentGridRow> {
  return {
    id: "__actions",
    header: "",
    enableSorting: false,
    enableResizing: false,
    size: 140,
    cell: ({ row }) => (
      <CorpusRowActions documentId={row.original.id} onDelete={() => onDelete(row.original.id)} onReingested={onReingested} />
    ),
  };
}
