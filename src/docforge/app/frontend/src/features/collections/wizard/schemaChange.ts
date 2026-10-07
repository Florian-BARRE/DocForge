// ====== Code Summary ======
// Pure helpers for saving an edited collection schema safely: build the PATCH payload (a `field_ops`
// list when a row was renamed so its stored values follow, else the legacy full `fields` list) and
// decide whether a dry-run `schema_diff` is destructive enough to need an explicit confirmation.

import type { FieldOp, FieldPatch, FieldSpec, SchemaDiff, UpdateCollectionRequest } from "../../../api/collections";
import { toFieldSpec, type DraftField } from "./wizardTypes";

const PATCHABLE_ATTRS: (keyof FieldPatch)[] = [
  "field_type", "required", "filterable", "lexical", "semantic", "enum_values", "origin", "scope", "description",
];

/** True when at least one row that was loaded from the collection now carries a different name. */
export function hasRenamedField(fields: DraftField[]): boolean {
  return fields.some((f) => f._originalName !== undefined && f._originalName !== f.field_name);
}

function changedAttrs(before: FieldSpec, after: FieldSpec): FieldPatch {
  const changes: Record<string, unknown> = {};
  for (const attr of PATCHABLE_ATTRS) {
    if (JSON.stringify(before[attr]) !== JSON.stringify(after[attr])) changes[attr] = after[attr];
  }
  return changes as FieldPatch;
}

/**
 * Explicit ops turning `original` into `current`, identity-tracked through `_originalName`:
 * removes first (frees names), then renames, then in-place updates under the new name, then adds.
 */
export function buildFieldOps(original: FieldSpec[], current: DraftField[]): FieldOp[] {
  const byOriginal = new Map(current.filter((f) => f._originalName !== undefined).map((f) => [f._originalName as string, f]));
  const ops: FieldOp[] = [];
  for (const spec of original) {
    if (!byOriginal.has(spec.field_name)) ops.push({ op: "remove", field_name: spec.field_name });
  }
  for (const spec of original) {
    const draft = byOriginal.get(spec.field_name);
    if (draft && draft.field_name !== spec.field_name) ops.push({ op: "rename", field_name: spec.field_name, new_name: draft.field_name });
  }
  for (const spec of original) {
    const draft = byOriginal.get(spec.field_name);
    if (!draft) continue;
    const changes = changedAttrs(spec, toFieldSpec(draft));
    if (Object.keys(changes).length > 0) ops.push({ op: "update", field_name: draft.field_name, changes });
  }
  for (const draft of current) {
    if (draft._originalName === undefined) ops.push({ op: "add", field: toFieldSpec(draft) });
  }
  return ops;
}

/** Swap the payload's full `fields` list for `field_ops` when a rename must keep its values. */
export function toUpdateRequest(payload: UpdateCollectionRequest, original: FieldSpec[], current: DraftField[]): UpdateCollectionRequest {
  if (!hasRenamedField(current)) return payload;
  const { fields: _fields, ...rest } = payload;
  void _fields;
  return { ...rest, field_ops: buildFieldOps(original, current) };
}

/** A diff needs confirmation when it deletes fields or any stored values. */
export function isDestructive(diff: SchemaDiff): boolean {
  const lost = Object.values(diff.values_lost ?? {}).some((count) => count > 0);
  return (diff.removed?.length ?? 0) > 0 || lost;
}
