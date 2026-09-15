// ====== Code Summary ======
// Module augmentation carrying the grid's own per-column facts (which filter control to render,
// its enum options, whether the value is a machine value that belongs in mono) on TanStack's
// column `meta` — the officially supported extension point for column-def-adjacent data.

import "@tanstack/react-table";
import type { ColumnFilterKind, ColumnGroup } from "./types";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    /** Which filter control the header filter row renders for this column; omitted = not filterable. */
    filterKind?: ColumnFilterKind;
    /** Fixed choices for an `enumMulti` filter (status/format or a schema `enum` field). */
    enumOptions?: string[];
    /** Render the cell value in JetBrains Mono (ids, sizes, dates, counts — brand rule). */
    mono?: boolean;
    align?: "left" | "right";
    /** The column-visibility menu section this column is listed under — also the grouped header
     *  row's family (GroupHeaderRow) and the filter panel's section (CorpusFilterPanel). */
    group?: ColumnGroup;
    /** Mirrors `filterKind !== undefined` explicitly, rather than deriving it, so the header's
     *  ColumnNatureBadges and the filter-panel legend can read one flat boolean. */
    filterable?: boolean;
    /** Metadata-only: this field has a `meta_<slug>_dense` vector — a query can target it for
     *  semantic search. Never set on a base column (dense vectors only exist for schema fields). */
    semantic?: boolean;
    /** Metadata-only: this field has a `meta_<slug>_bm25` vector — a query can target it for
     *  lexical/BM25 search. Never set on a base column. */
    lexical?: boolean;
  }
}
