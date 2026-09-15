// ====== Code Summary ======
// Presentation metadata for a column's origin family (`ColumnGroup`) — shared by the
// column-visibility menu, the grid's grouped header row (GroupHeaderRow) and the filter panel's
// section grouping (CorpusFilterPanel), so the three surfaces always agree on order/labels/tint.
// Document columns lead; the three metadata origins follow in the order a reader reasons about
// provenance (system-derived, then pipeline-generated, then user-declared).

import type { Column } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../../api/corpus";
import { theme } from "../../../theme";
import type { ColumnGroup } from "../types";

export const COLUMN_GROUP_ORDER: ColumnGroup[] = ["document", "system", "generated", "user"];

// Longer-form labels for the column-visibility menu, where each group is its own labelled section
// with room to spell out "metadata"/"upload metadata".
export const COLUMN_GROUP_LABELS: Record<ColumnGroup, string> = {
  document: "Document",
  system: "System metadata",
  generated: "Generated metadata",
  user: "Upload metadata",
};

export interface GroupHeaderInfo {
  /** Short family name for the grid's grouped header band and the filter panel's section title. */
  label: string;
  /** One-line provenance caption shown under the label in the grouped header band. */
  caption: string;
  /** Soft background tint for the grouped header band. `transparent` for `document`: it's the
   *  anchor/home block, deliberately left neutral rather than tinted. */
  tint: string;
  /** Top-accent border colour for the grouped header band — one step stronger than `tint`. */
  accent: string;
}

// Tint/accent reuse existing semantic tokens rather than inventing new ones, and mirror the origin
// tones already established for metadata elsewhere in the app (MetadataTable.tsx: generated→loop,
// system→warn) — `user` reuses `capability`, the token whose own theme.ts comment already names
// "user"-authored fields as one of the things it exists to tag.
export const GROUP_HEADER_INFO: Record<ColumnGroup, GroupHeaderInfo> = {
  document: { label: "Document", caption: "identity & state", tint: "transparent", accent: theme.color.line },
  system: { label: "System", caption: "computed at ingestion", tint: theme.color.warnSoft, accent: theme.color.warnStrong },
  user: { label: "Metadata", caption: "entered at ingestion", tint: theme.color.capabilitySoft, accent: theme.color.capabilityStrong },
  generated: { label: "Generated", caption: "produced by the pipeline", tint: theme.color.loopSoft, accent: theme.color.loopStrong },
};

/** Buckets a set of grid columns by their `meta.group` (defaulting to `"document"` for a column
 *  that never set one — chrome columns are filtered out by callers before reaching this). */
export function groupColumnsByOrigin(
  columns: Column<DocumentGridRow, unknown>[],
): Partial<Record<ColumnGroup, Column<DocumentGridRow, unknown>[]>> {
  const grouped: Partial<Record<ColumnGroup, Column<DocumentGridRow, unknown>[]>> = {};
  for (const column of columns) {
    const group = column.columnDef.meta?.group ?? "document";
    (grouped[group] ??= []).push(column);
  }
  return grouped;
}
