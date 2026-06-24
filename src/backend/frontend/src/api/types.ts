// ====== Code Summary ======
// Public API types — re-exported from the auto-generated OpenAPI schemas so the
// frontend never drifts from the Pydantic models on the backend.
//
//   Regenerate with:    npm run gen:types
//   (env: OPENAPI_URL — e.g. http://docforge:8000/openapi.json in dev container)
//
// This file ONLY contains:
//   • short aliases over `components['schemas']['…']` so callsites stay terse;
//   • literal-narrowing overlays where Pydantic loses information at the wire
//     (e.g. the document status enum — Python uses a free str, the UI deals
//     with a closed union);
//   • UI-only types that have no Pydantic equivalent (filter/picker shapes
//     internal to React components).
//
// Anything that ALSO exists on the backend must come from `generated.ts` —
// adding a new hand-written interface here is a regression.

import type { components } from './generated'

type Schemas = components['schemas']

// ── Discovery ─────────────────────────────────────────────────────────────────
//
// The Pydantic discovery models use ``ConfigDict(extra="allow")`` which causes
// openapi-typescript to emit ``& { [key: string]: unknown }`` index signatures.
// Those index signatures bleed through Omit<...> and poison every property
// access (TS resolves `field.field_path` to `unknown` even when the schema
// declares it as `string`).  We use ``Pick<>`` to keep only the documented
// fields — the index signature is silently dropped — then re-add the few
// fields we want to narrow further (chains, enums, …).

export interface ParamSchema {
  name: string
  type: string
  label: string
  default?: unknown
  description: string
  min?: number | null
  max?: number | null
  enum?: string[] | null
  [extra: string]: unknown
}

export interface Choice {
  id: string
  label: string
  available: boolean
  selectable: boolean
  default: boolean
  note: string
  fields: ParamSchema[]
}

export interface DynamicField {
  field_path: string
  capability: string
  kind: DynamicFieldKind
  scope: DynamicFieldScope
  resolved: boolean
  choices: Choice[]
  note: string
}

export interface ContractRef {
  content_type: string
  schema_ref?: string | null
  status?: string | null
}

export interface FieldDescriptor {
  name: string
  type?: string | null
  required: boolean
  default?: unknown
  min?: number | null
  max?: number | null
  enum?: string[] | null
  description: string
}

export interface EndpointDescriptor {
  operation: Schemas['OperationRef']
  route_name: string
  tags: string[]
  summary: string
  description: string
  path_params: FieldDescriptor[]
  query_params: FieldDescriptor[]
  input?: ContractRef | null
  output?: ContractRef | null
  dynamic_fields: DynamicField[]
}

export interface DiscoveryResponse {
  openapi_version: string
  collection_id?: string | null
  endpoints: EndpointDescriptor[]
  components: { schemas: Record<string, unknown> }
}

// Discovery uses `str` for `kind` / `scope` so OpenAPI can't emit a TS union —
// keep these closed unions in sync with `discovery/overlays.py` if you add a kind.
export type DynamicFieldKind = 'single' | 'multi' | 'optional' | 'map' | 'weights' | 'scalar'
export type DynamicFieldScope = 'deployment' | 'collection'

// ── Health ────────────────────────────────────────────────────────────────────

export type HealthResponse = Schemas['HealthResponse']

// ── Chain provenance (Phase A) ────────────────────────────────────────────────

export type ChainAttempt = Schemas['ChainAttemptIR']
export type ChainTrace = Schemas['ChainTrace']

// ── Collections ───────────────────────────────────────────────────────────────

export type Collection = Schemas['CollectionResponse']
export type CollectionListResponse = Schemas['CollectionListResponse']

// ── Config ────────────────────────────────────────────────────────────────────

export type MetaField = Schemas['ConfigMetaField']
export type AppliedIssue = Schemas['AppliedIssue']
// reindex_reasons overlays the generated type until the next `npm run gen:types`:
// exact, human-readable causes of a required reindex (empty for non-critical changes).
export type ConfigApplied = Schemas['ConfigApplied'] & {
  reindex_reasons?: string[] | null
}
// embed_provider_id is added server-side on the same response shape.
// The intersection keeps this in sync when generated.ts is next regenerated.
export type ConfigState = Schemas['ConfigStateResponse'] & { embed_provider_id: string }
export type ConfigSchemaResponse = Schemas['ConfigSchemaResponse']
export type ConfigVersionSummary = Schemas['ConfigVersionSummary']
export type ConfigHistoryResponse = Schemas['ConfigHistoryResponse']

// ── Documents ─────────────────────────────────────────────────────────────────

// The backend normalises status at the API boundary to {pending,running,done,error}.
// Pydantic types it as `str` though, so we narrow on the way in.
export type DocStatus = 'pending' | 'running' | 'done' | 'error'
// stale / stale_reasons overlay the generated type until the next `npm run gen:types`:
// precise, reversible staleness vs the collection's current config (see backend
// DocumentStaleness). Prefer these over comparing pipeline_version numbers.
export type Document = Omit<Schemas['DocumentResponse'], 'status'> & {
  status: DocStatus
  stale?: boolean
  stale_reasons?: string[]
}
export type DocumentListResponse = Omit<Schemas['DocumentListResponse'], 'documents'> & {
  documents: Document[]
}
export type IngestResponse = Schemas['IngestResponse']
export type MetadataUpdateResponse = Schemas['MetadataUpdateResponse']
export type ReingestResponse = Schemas['ReingestResponse']
export type DocumentDeleteResponse = Schemas['DocumentDeleteResponse']
export type PresignedUrlResponse = Schemas['PresignedUrlResponse']

// ── Chunks ────────────────────────────────────────────────────────────────────

export type ChunkResponse = Schemas['ChunkResponse']
export type ChunkListResponse = Schemas['ChunkListResponse']
export type ChunkUpdateResponse = Schemas['ChunkUpdateResponse']

// ── Pages ─────────────────────────────────────────────────────────────────────

export type PageInfo = Schemas['PageInfo']
export type PageListResponse = Schemas['PageListResponse']
export type BlockInfo = Schemas['BlockInfo']
export type PageDetailResponse = Schemas['PageDetailResponse']
export type PageReingestResponse = Schemas['PageReingestResponse']

// ── Search ────────────────────────────────────────────────────────────────────

// Extend the generated type with vector_ranks (added in debug mode — P6.x).
// The generated schema may not include this field until the next `npm run gen:types`
// run against a rebuilt container, so we add the overlay here to unblock the UI.
export type SearchResultItem = Schemas['SearchResultItem'] & {
  /** Per-vector name → 1-indexed rank in that vector's candidate list (debug mode only). */
  vector_ranks?: Record<string, number> | null
  /** Per-query debug info populated when SearchRequest.debug is true. */
  debug_info?: Record<string, unknown> | null
}
// A document group, present when pipeline.search.retrieve.grouping is enabled.
export interface SearchGroupItem {
  document_id: string
  score: number
  chunks: SearchResultItem[]
}

// Extend SearchResponse with debug_info + groups (overlays until the next types
// regeneration runs against a rebuilt container).
export type SearchResponse = Schemas['SearchResponse'] & {
  debug_info?: Record<string, unknown> | null
  /** Document-level groups, present only when grouping is enabled. */
  groups?: SearchGroupItem[] | null
  /** Informational note (e.g. sparse/BM25 unavailable on a dense-only provider). */
  note?: string | null
}

// ── Re-export everything from the generated namespace for callers that prefer
// the verbose path (e.g. `import type { components } from '../../api/types'`).
export type { components } from './generated'
