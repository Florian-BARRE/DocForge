// ====== Code Summary ======
// Dynamic columns built from the collection's document-metadata schema (GET /collections/{id}
// .fields) — this is what makes an added Pydantic metadata field surface in the grid automatically,
// with zero further frontend edit. Chunk-scoped fields are skipped: they never appear in a
// document row's `metadata` map. Only `filterable` fields get a header filter control.

import type { ColumnDef } from "@tanstack/react-table";
import type { FieldSpec, FieldType } from "../../../api/collections";
import type { DocumentGridRow } from "../../../api/corpus";
import { MetadataValueCell } from "../MetadataValueCell";
import { metadataColumnId, type ColumnFilterKind } from "../types";

function filterKindFor(fieldType: FieldType): ColumnFilterKind | undefined {
  switch (fieldType) {
    case "string":
    case "text":
      return "text";
    case "enum":
      return "enumMulti";
    case "bool":
      return "bool";
    case "integer":
    case "float":
      return "numberRange";
    case "datetime":
      return "dateRange";
    case "keyword_list":
    case "text_list":
    case "integer_list":
    case "float_list":
      return "listIn";
    default:
      return undefined;
  }
}

export function buildMetadataColumns(fields: FieldSpec[]): ColumnDef<DocumentGridRow>[] {
  return fields
    .filter((field) => field.scope === "document")
    .map((field) => {
      const filterKind = field.filterable ? filterKindFor(field.field_type) : undefined;
      return {
        id: metadataColumnId(field.field_name),
        header: field.field_name,
        meta: {
          group: field.origin,
          ...(filterKind ? { filterKind, enumOptions: field.enum_values ?? undefined } : {}),
        },
        accessorFn: (row) => row.metadata[field.field_name],
        cell: ({ row }) => <MetadataValueCell value={row.original.metadata[field.field_name]} />,
      } satisfies ColumnDef<DocumentGridRow>;
    });
}
