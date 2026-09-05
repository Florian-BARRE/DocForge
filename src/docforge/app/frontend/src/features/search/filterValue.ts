// ====== Code Summary ======
// Pure helpers behind the Search Lab filter builder — which operator modes a field type supports,
// and the shapes that carry them. The wire contract (SearchRequest.filters in
// app/backend/routers/search/models.py, backed by shared_libs' qdrant/vectors/filters.py) accepts,
// per field, a SCALAR (equality Match), a LIST (set-membership MatchAny, any-of), or a MAPPING of
// gte/gt/lte/lt bounds (a Range) — a range is only accepted on an integer/float/datetime-typed
// field. These helpers never invent a shape beyond that trio.

import type { FieldType } from "../../api/collections";

export type FilterMode = "eq" | "any" | "range";

/** The four range bound keys the backend accepts, verbatim — see RANGE_KEYS in filters.py. */
export interface RangeValue {
  gte?: number | string;
  gt?: number | string;
  lte?: number | string;
  lt?: number | string;
}

// Mirrors DatabaseHelpers.PAYLOAD_TYPES → SearchHelpers._RANGE_TYPED: only these field types index
// to an INTEGER/FLOAT/DATETIME Qdrant payload type, the only ones a Range can constrain.
const RANGE_TYPED: ReadonlySet<FieldType> = new Set([
  "integer", "float", "datetime", "integer_list", "float_list",
]);

// A two-valued field never benefits from any-of/range; keep it exact-only for a simpler control.
const EXACT_ONLY: ReadonlySet<FieldType> = new Set(["bool"]);

/** Which operator modes a field's declared type may express, in display order. */
export function modesForFieldType(fieldType: FieldType): FilterMode[] {
  const modes: FilterMode[] = ["eq"];
  if (!EXACT_ONLY.has(fieldType)) modes.push("any");
  if (RANGE_TYPED.has(fieldType)) modes.push("range");
  return modes;
}

/** Whether a field's values are numbers on the wire (drives number vs. text inputs/parsing). */
export function isNumericFieldType(fieldType: FieldType): boolean {
  return fieldType === "integer" || fieldType === "float"
    || fieldType === "integer_list" || fieldType === "float_list";
}

/** Infers which mode a live filter value is currently expressed in. */
export function modeOfValue(value: unknown): FilterMode {
  if (Array.isArray(value)) return "any";
  if (value !== null && typeof value === "object") return "range";
  return "eq";
}

export const RANGE_KEYS: readonly (keyof RangeValue)[] = ["gte", "gt", "lte", "lt"];

/** Drops undefined bounds; returns undefined (never an empty object) when nothing is left. */
export function cleanRange(range: RangeValue): RangeValue | undefined {
  const entries = RANGE_KEYS
    .map((key) => [key, range[key]] as const)
    .filter(([, v]) => v !== undefined);
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}
