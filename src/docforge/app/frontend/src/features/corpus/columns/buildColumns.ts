// ====== Code Summary ======
// Assembles the grid's full column set: selection checkbox, fixed base columns, dynamic metadata
// columns (schema-driven), then row actions. The single composition point CorpusPage calls.

import type { ColumnDef } from "@tanstack/react-table";
import type { FieldSpec } from "../../../api/collections";
import type { DocumentGridRow } from "../../../api/corpus";
import type { UseSelectionResult } from "../useSelection";
import { buildActionsColumn } from "./actionsColumn";
import { buildBaseColumns } from "./baseColumns";
import { buildMetadataColumns } from "./metadataColumns";
import { buildSelectColumn } from "./selectColumn";

interface BuildColumnsArgs {
  selection: UseSelectionResult;
  fields: FieldSpec[];
  supportedFormats: string[];
  onOpen: (documentId: string) => void;
  onEnabledChanged: (documentId: string, enabled: boolean) => void;
  onDelete: (documentId: string) => Promise<void>;
  onReingested: () => void;
}

export function buildColumns(args: BuildColumnsArgs): ColumnDef<DocumentGridRow>[] {
  const { selection, fields, supportedFormats, onOpen, onEnabledChanged, onDelete, onReingested } = args;
  return [
    buildSelectColumn(selection),
    ...buildBaseColumns({ onOpen, onEnabledChanged, supportedFormats }),
    ...buildMetadataColumns(fields),
    buildActionsColumn({ onDelete, onReingested }),
  ];
}
