// ====== Code Summary ======
// Local per-column filter state shapes for the corpus grid, plus the metadata-column id
// convention (a `meta:` prefix so a metadata field can never collide with a base column name)
// and the helpers that strip it back to the raw field name the API expects.

export const METADATA_PREFIX = "meta:";

export type ColumnFilterKind = "text" | "enumMulti" | "bool" | "numberRange" | "dateRange" | "listIn";

/** Which section of the column-visibility menu a column belongs to. */
export type ColumnGroup = "document" | "system" | "generated" | "user";

export interface TextFilterValue { kind: "text"; contains: string }
export interface EnumFilterValue { kind: "enumMulti"; values: string[] }
export interface BoolFilterValue { kind: "bool"; value: boolean | null }
export interface NumberRangeFilterValue { kind: "numberRange"; gte: string; lte: string }
export interface DateRangeFilterValue { kind: "dateRange"; gte: string; lte: string }
export interface ListFilterValue { kind: "listIn"; values: string[] }

export type ColumnFilterValue =
  | TextFilterValue
  | EnumFilterValue
  | BoolFilterValue
  | NumberRangeFilterValue
  | DateRangeFilterValue
  | ListFilterValue;

/** Keyed by TanStack column id — absent entries mean "no filter applied on this column". */
export type ColumnFiltersState = Record<string, ColumnFilterValue>;

export function emptyFilterValue(kind: ColumnFilterKind): ColumnFilterValue {
  switch (kind) {
    case "text": return { kind, contains: "" };
    case "enumMulti": return { kind, values: [] };
    case "bool": return { kind, value: null };
    case "numberRange": return { kind, gte: "", lte: "" };
    case "dateRange": return { kind, gte: "", lte: "" };
    case "listIn": return { kind, values: [] };
  }
}

/** A metadata column's TanStack id — prefixed so it never collides with a base column name. */
export function metadataColumnId(fieldName: string): string {
  return `${METADATA_PREFIX}${fieldName}`;
}

/** The raw field name the API expects (filter clause key or sort field) for a given column id. */
export function apiFieldName(columnId: string): string {
  return columnId.startsWith(METADATA_PREFIX) ? columnId.slice(METADATA_PREFIX.length) : columnId;
}

export function isMetadataColumn(columnId: string): boolean {
  return columnId.startsWith(METADATA_PREFIX);
}

// The selection checkbox and row-actions columns are structural chrome, not data — they stay
// pinned first/last and are excluded from both drag-reorder and resize.
export const PINNED_FIRST_COLUMN_ID = "__select";
export const PINNED_LAST_COLUMN_ID = "__actions";

export function isPinnedColumn(columnId: string): boolean {
  return columnId === PINNED_FIRST_COLUMN_ID || columnId === PINNED_LAST_COLUMN_ID;
}
