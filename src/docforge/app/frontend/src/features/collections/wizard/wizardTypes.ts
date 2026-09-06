// ====== Code Summary ======
// The wizard's draft state shape + the MB/bytes conversion the size-limit step needs. Kept
// separate from api/collections.ts because `_key` below is a client-only list key, never sent
// to the backend. Also holds the edit-mode helpers: prefilling drafts from an existing
// Collection, and diffing against the original schema to warn about field removal.

import type { Collection, CreateCollectionRequest, FieldSpec } from "../../../api/collections";

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

// Collection response keys that already have a named wizard state slot, or are structural
// (never part of the identity/limits contract schema StepIdentity renders) — everything else on
// the loaded collection is a contract field the wizard doesn't know about by name yet.
const NAMED_OR_STRUCTURAL_KEYS = new Set([
  "id", "name", "supported_formats", "tags", "max_file_size_bytes", "job_timeout_seconds",
  "needs_reindex", "created_at", "pipeline", "search", "fields",
]);

/**
 * Any collection field beyond the wizard's named slots — kept verbatim so a future
 * `CollectionContractModel` addition still shows its stored value (not the schema default) when
 * editing, even before it earns its own named state. Runtime-only: such a key isn't declared on
 * the `Collection` TS type until the frontend is updated to match the backend contract.
 */
function extraContractFromCollection(collection: Collection): Record<string, unknown> {
  const extra: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(collection)) {
    if (!NAMED_OR_STRUCTURAL_KEYS.has(key)) extra[key] = value;
  }
  return extra;
}

/** Prefill every editable draft slice from an existing collection — the edit wizard's starting point. */
export function draftFromCollection(collection: Collection): {
  name: string;
  formats: string[];
  tags: string[];
  maxSizeMb: number;
  jobTimeoutSeconds: number | null;
  fields: DraftField[];
  extraContract: Record<string, unknown>;
} {
  return {
    name: collection.name,
    formats: [...collection.supported_formats],
    tags: [...collection.tags],
    maxSizeMb: bytesToMb(collection.max_file_size_bytes),
    jobTimeoutSeconds: collection.job_timeout_seconds,
    fields: collection.fields.map(toDraftField),
    extraContract: extraContractFromCollection(collection),
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

/** The named wizard state slices that assemble into the submitted contract — everything
 *  `buildWizardPayload` needs, short of the create-only `preset`. */
export interface WizardDraftSlices {
  extraContract: Record<string, unknown>;
  name: string;
  formats: string[];
  tags: string[];
  maxSizeMb: number;
  jobTimeoutSeconds: number | null;
  fields: DraftField[];
}

/**
 * Assemble the exact collection contract payload the wizard would submit right now — named state
 * + schema fields + whatever untyped contract fields StepIdentity's schema-driven form is
 * carrying. Shared by the actual submit call and the live preview panel so the two can never
 * drift apart (the preview is always byte-identical to what "Create"/"Save" would send).
 */
export function buildWizardPayload(draft: WizardDraftSlices): CreateCollectionRequest {
  return {
    ...draft.extraContract,
    name: draft.name.trim(),
    supported_formats: draft.formats,
    tags: draft.tags,
    max_file_size_bytes: mbToBytes(draft.maxSizeMb),
    job_timeout_seconds: draft.jobTimeoutSeconds,
    fields: draft.fields.map(toFieldSpec),
  };
}
