// ====== Code Summary ======
// The wizard's draft state shape + the MB/bytes conversion the size-limit step needs. Kept
// separate from api/collections.ts because `_key` below is a client-only list key, never sent
// to the backend. Also holds the edit-mode helpers: prefilling drafts from an existing
// Collection, and diffing against the original schema to warn about field removal.

import type { Collection, FieldSpec } from "../../../api/collections";

const BYTES_PER_MB = 1024 * 1024;

export function mbToBytes(mb: number): number {
  return Math.round(mb * BYTES_PER_MB);
}

export function bytesToMb(bytes: number): number {
  return bytes / BYTES_PER_MB;
}

/** One schema row being edited — `_key` is a stable React list key, stripped before submit. */
export interface DraftField extends FieldSpec {
  _key: string;
}

let nextKey = 0;

export function blankField(): DraftField {
  nextKey += 1;
  return {
    _key: `draft-${nextKey}`,
    field_name: "",
    field_type: "string",
    required: false,
    filterable: false,
    lexical: false,
    semantic: false,
    enum_values: null,
    origin: "user",
    scope: "document",
  };
}

/** Strip the client-only key before the payload goes to the API. */
export function toFieldSpec({ _key, ...rest }: DraftField): FieldSpec {
  void _key;
  return rest;
}

/** Wrap an existing field spec (from a fetched Collection) as an editable draft row. */
export function toDraftField(spec: FieldSpec): DraftField {
  nextKey += 1;
  return { ...spec, _key: `draft-${nextKey}` };
}

/** Prefill every editable draft slice from an existing collection — the edit wizard's starting point. */
export function draftFromCollection(collection: Collection): {
  name: string;
  formats: string[];
  maxSizeMb: number;
  fields: DraftField[];
} {
  return {
    name: collection.name,
    formats: [...collection.supported_formats],
    maxSizeMb: bytesToMb(collection.max_file_size_bytes),
    fields: collection.fields.map(toDraftField),
  };
}

/**
 * Field names present in the original schema but missing from the current draft — the backend
 * deletes these fields (and every stored value) when the target schema is submitted.
 */
export function removedFieldNames(original: FieldSpec[], current: DraftField[]): string[] {
  const kept = new Set(current.map((f) => f.field_name));
  return original.filter((f) => !kept.has(f.field_name)).map((f) => f.field_name);
}
