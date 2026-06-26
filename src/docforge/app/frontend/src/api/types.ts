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

// ── Config tree (recursive discovery — CHUNK D2) ─────────────────────────────
//
// The backend emits a `config_tree: ConfigNode` on config-bearing endpoints
// (create_collection, update_config).  This is a recursive tree where each node
// is tagged by `kind` and describes one field or sub-group of the PipelineConfig.
// The tree replaces the flat `dynamic_fields` for config panels; flat fields
// remain for other overlays (filters, weights, metadata).

/** A single provider choice within a chain or provider_union node. */
export interface ProviderChoice {
  id: string
  label: string
  available: boolean
  selectable: boolean
  /** True when this choice is the deployment-default (first available) */
  default: boolean
  note: string
  /** Recursive sub-config fields for this provider. */
  params: ConfigNode[]
}

/**
 * One node in the recursive config tree emitted by the backend discovery endpoint.
 * Kinds map to their rendering strategy in RecursiveFieldRenderer.
 */
export interface ConfigNode {
  /** Absolute dot-path, e.g. "patch.pipeline.embed.gate.min_score". */
  path: string
  /** Discriminator that drives the rendering dispatch. */
  kind: 'scalar' | 'enum' | 'object' | 'chain' | 'provider_union'
  label: string
  description: string
  default: unknown
  /** False when a collection_id is needed but was not provided. */
  resolved: boolean

  // ── kind=scalar ──
  type?: 'bool' | 'int' | 'float' | 'str' | 'secret' | string | null
  min?: number | null
  max?: number | null

  // ── kind=enum ──
  options?: string[] | null

  // ── kind=object ──
  children?: ConfigNode[] | null

  // ── kind=chain / provider_union ──
  /** True for chains (multi-provider), false for single provider_union. */
  multi?: boolean | null
  /** True when the union may be unset (adds a "disabled" chip). */
  optional?: boolean | null
  /** Registry category (parser / embed / rerank / llm / …). */
  capability?: string | null
  choices?: ProviderChoice[] | null
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
  /** Recursive config tree for config-bearing endpoints (create_collection, update_config). */
  config_tree?: ConfigNode | null
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

// ── Jobs ──────────────────────────────────────────────────────────────────────
//
// Hand-written because `jobs` was added to DocumentResponse after the last
// `npm run gen:types` run.  Mirrors the backend JobResponse Pydantic model exactly.
// Regenerate `generated.ts` to absorb this when the schema stabilises.

export type JobStatus = 'pending' | 'running' | 'done' | 'failed'

export interface JobResponse {
  id: string
  document_id: string
  collection_id: string
  status: JobStatus
  error: string | null
  created_at: string
  worker_id: string | null
  started_at: string | null
  finished_at: string | null
  attempt: number
  current_stage: string | null
  progress: number
  arq_status: string | null
}

// ── Documents ─────────────────────────────────────────────────────────────────

// The backend normalises status at the API boundary to {pending,running,done,error}.
// Pydantic types it as `str` though, so we narrow on the way in.
export type DocStatus = 'pending' | 'running' | 'done' | 'error'
// stale / stale_reasons overlay the generated type until the next `npm run gen:types`:
// precise, reversible staleness vs the collection's current config (see backend
// DocumentStaleness). Prefer these over comparing pipeline_version numbers.
// jobs / chain_traces / embed_chain_traces: also added server-side after the last gen.
export type Document = Omit<Schemas['DocumentResponse'], 'status'> & {
  status: DocStatus
  stale?: boolean
  stale_reasons?: string[]
  /** Full job history newest-first (ingestion + reingestions + retries). */
  jobs?: JobResponse[]
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

// ── Auth ──────────────────────────────────────────────────────────────────────
//
// Hand-written types because the auth router was added after the last
// `npm run gen:types` run.  These mirror the Pydantic models exactly.
// Regenerate `generated.ts` when the backend schema stabilises.

export interface UserSummary {
  id: string
  username: string
  /** 'root' | 'user' */
  role: string
  is_active: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserSummary
}

export interface CollectionGrantSummary {
  collection_id: string
  /** 'read' | 'write' | 'admin' */
  role: string
}

export interface MeResponse {
  user: UserSummary
  grants: CollectionGrantSummary[]
}

// ── API keys ───────────────────────────────────────────────────────────────

export interface ApiKeyCreatedResponse {
  id: string
  name: string
  prefix: string
  /** Plaintext key — shown ONCE on creation, never retrievable again. */
  key: string
  created_at: string
}

export interface ApiKeySummary {
  id: string
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

export interface ApiKeyListResponse {
  keys: ApiKeySummary[]
  total: number
}

export interface ApiKeyRevokeResponse {
  revoked: boolean
  id: string
}

// ── Users (root only) ─────────────────────────────────────────────────────

export interface UserResponse {
  id: string
  username: string
  role: string
  is_active: boolean
  created_at: string
}

export interface UserListResponse {
  users: UserResponse[]
  total: number
}

export interface DeactivateUserResponse {
  deactivated: boolean
  id: string
}

/** Response from POST /users/{id}/impersonate (root only). */
export interface ImpersonateResponse {
  access_token: string
  token_type: string
  user: UserSummary
}

// ── Collection access ─────────────────────────────────────────────────────

export interface AccessGrantResponse {
  user_id: string
  username: string | null
  /** 'read' | 'write' | 'admin' */
  role: string
  granted_by: string | null
  created_at: string
}

export interface AccessListResponse {
  collection_id: string
  grants: AccessGrantResponse[]
  total: number
}

export interface RevokeAccessResponse {
  revoked: boolean
  collection_id: string
  user_id: string
}

// ── Re-export everything from the generated namespace for callers that prefer
// the verbose path (e.g. `import type { components } from '../../api/types'`).
export type { components } from './generated'
