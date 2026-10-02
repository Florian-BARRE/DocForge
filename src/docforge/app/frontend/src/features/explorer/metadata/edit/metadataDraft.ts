// ====== Code Summary ======
// Pure helpers behind the document metadata editor: which schema fields are editable, the initial
// draft from the document's current values, the changed-only diff sent to the PATCH, and the
// mapping of the backend's per-field 422 messages onto field names. No React, no I/O.

import type { FieldSpec } from "../../../../api/collections";
import type { MetadataValue } from "../../../../api/explorer";

export type DraftValues = Record<string, unknown>;

/** Editable = document-scope USER or GENERATED fields (chunk-scope is reindex-required; system is derived). */
export function isEditableField(field: FieldSpec): boolean {
  return field.scope === "document" && (field.origin === "user" || field.origin === "generated");
}

/** Schema fields that are chunk-scope — shown as a read-only note, never editable here. */
export function chunkScopeFields(fields: FieldSpec[]): FieldSpec[] {
  return fields.filter((field) => field.scope === "chunk" && field.origin !== "system");
}

/** Current stored values keyed by field name — the editor's baseline. */
export function currentValues(metadata: MetadataValue[]): DraftValues {
  const values: DraftValues = {};
  for (const entry of metadata) values[entry.field_name] = entry.value;
  return values;
}

/** Treats undefined / null / "" / [] as the same "empty" so an untouched blank never counts as an edit. */
function normalize(value: unknown): unknown {
  if (value === undefined || value === null || value === "") return null;
  if (Array.isArray(value) && value.length === 0) return null;
  return value;
}

function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(normalize(a)) === JSON.stringify(normalize(b));
}

/** Only the fields whose draft differs from the baseline — the exact PATCH payload. An emptied field is sent as null. */
export function changedValues(fields: FieldSpec[], baseline: DraftValues, draft: DraftValues): DraftValues {
  const changed: DraftValues = {};
  for (const field of fields) {
    const name = field.field_name;
    if (!sameValue(baseline[name], draft[name])) changed[name] = normalize(draft[name]);
  }
  return changed;
}

/** Splits 422 messages into per-field errors (the backend quotes the name: `field 'x' …`) and the unattributed rest. */
export function mapFieldErrors(messages: string[], fieldNames: string[]): { byField: Record<string, string>; general: string[] } {
  const byField: Record<string, string> = {};
  const general: string[] = [];
  for (const message of messages) {
    const owner = fieldNames.find((name) => message.includes(`'${name}'`));
    if (owner && !byField[owner]) byField[owner] = message;
    else general.push(message);
  }
  return { byField, general };
}

/** Folds saved values into the document's resolved metadata list, keeping the stored origin (or the spec's for a new row). */
export function mergeSavedMetadata(metadata: MetadataValue[], updated: DraftValues, specs: FieldSpec[]): MetadataValue[] {
  const next = metadata.map((entry) => (entry.field_name in updated ? { ...entry, value: updated[entry.field_name] } : entry));
  const present = new Set(metadata.map((entry) => entry.field_name));
  for (const [name, value] of Object.entries(updated)) {
    const spec = specs.find((s) => s.field_name === name);
    if (!present.has(name) && spec) next.push({ field_name: name, value, origin: spec.origin });
  }
  return next;
}
