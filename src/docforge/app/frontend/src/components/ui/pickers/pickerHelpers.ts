// ====== Code Summary ======
// Shared types and pure helpers for the ChoicePicker sub-pickers.
// Holds the common PickerValue shape, nested-provider mapping, and the small
// path/defaults utilities reused across SinglePicker, MultiPicker, etc.

// ====== Internal Project Imports ======
import type { ParamSchema } from '../../../api/types'

// DynamicField kinds recognized by the dispatcher.  The backend may introduce new ones via
// `discovery/overlays.py::_pipeline_dynamic_fields` — add a branch in ChoicePicker.
//   single   — radio chip group, selected option shows its conditional fields.
//   optional — single + a "disabled" chip clears the selection.
//   multi    — ordered list builder (e.g. OCR escalation chain).
//   map      — key→value editor (search filters, ingest metadata).
//   weights  — float slider per named vector.
//   scalar   — single typed scalar input (bool / int / float / str) for stage-level params.

/**
 * Selected provider/method value as stored on the wire and in configState.
 *
 * The backend expects (and returns) a flat object: { id, param1, param2, … }.
 * There is NO nested `params` sub-object — all provider params sit alongside `id`.
 * Keeping this shape in the pickers guarantees that the patch sent to the backend
 * exactly matches what configState returns, so read/write round-trips are lossless.
 */
export interface PickerValue {
  id: string
  [param: string]: unknown
}

// ── Nested provider picker plumbing ──────────────────────────────────────────
//
// When a typed config carries a sub-field that is itself a discriminated provider
// union (e.g. SemanticConfig.embed: EmbedProviderConfig), the discovery payload
// can't naturally fit the union under the parent field's ParamSchema.  We detect
// these cases by name and reuse the matching root-level overlay's choices.
//
// Mapping: parent capability → child field name → child capability we should
// surface as a single-picker.
export const NESTED_PROVIDER_FIELDS: Record<string, Record<string, string>> = {
  split_method: { embed: 'embed' },
}

/**
 * Resolve the nested capability id for a (parentCapability, childFieldName) pair.
 *
 * Args:
 *   parentCapability: Capability of the field carrying the nested union.
 *   childField:       Name of the sub-field that is itself a provider union.
 *
 * Returns:
 *   The nested capability id, or null when no nested mapping exists.
 */
export function nestedCapabilityFor(parentCapability: string, childField: string): string | null {
  return NESTED_PROVIDER_FIELDS[parentCapability]?.[childField] ?? null
}

/**
 * Build the default params object from a choice's field schemas.
 *
 * Args:
 *   fields: Param schema descriptors of the selected choice.
 *
 * Returns:
 *   A record mapping field name → default value, omitting null/undefined defaults.
 */
export function paramsDefaults(fields: ParamSchema[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  fields.forEach(f => { if (f.default !== undefined && f.default !== null) out[f.name] = f.default })
  return out
}

/**
 * Derive a human-readable label from a dotted field path.
 *
 * Args:
 *   path: Dotted field path (e.g. "enrich.split_method").
 *
 * Returns:
 *   A title-cased label built from the last path segment.
 */
export function labelFromPath(path: string): string {
  const last = path.split('.').pop() ?? path
  return last.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
