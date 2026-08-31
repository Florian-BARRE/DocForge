// ====== Code Summary ======
// Module augmentation carrying the grid's own per-column facts (which filter control to render,
// its enum options, whether the value is a machine value that belongs in mono) on TanStack's
// column `meta` — the officially supported extension point for column-def-adjacent data.

import "@tanstack/react-table";
import type { ColumnFilterKind } from "./types";

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
  }
}
