// ====== Code Summary ======
// TypeScript mirror of the collections REST contract + its typed client. Shapes copied verbatim
// from the backend's Pydantic models (see /openapi.json) — nothing invented.

import { apiFetch, jsonInit } from "./http";
import type { JsonSchema } from "./types";

const BASE = "/api/v1/collections";

// mirror of backend StrEnums (app/backend/routers/collections/models.py) — keep in sync; no
// discovery/enums endpoint currently exposes these, so they stay hand-copied until one does.
export type FieldType = "string" | "integer" | "float" | "bool" | "keyword_list" | "datetime" | "enum" | "text" | "integer_list" | "float_list" | "text_list";
export type FieldOrigin = "system" | "user" | "generated";
export type FieldScope = "document" | "chunk";

/** Canonical value lists (mirrors the backend StrEnums) — every select renders from these, never from an inline literal. */
export const FIELD_TYPES: FieldType[] = ["string", "integer", "float", "bool", "keyword_list", "datetime", "enum", "text", "integer_list", "float_list", "text_list"];
export const FIELD_ORIGINS: FieldOrigin[] = ["system", "user", "generated"];
export const FIELD_SCOPES: FieldScope[] = ["document", "chunk"];

export interface FieldSpec {
  field_name: string;
  field_type: FieldType;
  required: boolean;
  filterable: boolean;
  lexical: boolean;
  semantic: boolean;
  enum_values: string[] | null;
  origin: FieldOrigin;
  scope: FieldScope;
}

export interface Collection {
  id: string;
  name: string;
  supported_formats: string[];
  max_file_size_bytes: number;
  /** Whole-ingest-job wall-clock budget override, in seconds; `null` inherits the worker's global default. */
  job_timeout_seconds: number | null;
  needs_reindex: boolean;
  created_at: string | null;
  pipeline: Record<string, unknown>;
  search: Record<string, unknown>;
  fields: FieldSpec[];
}

/** Stock ingestion pipeline a new collection starts on when no explicit `pipeline` is posted. */
export type CollectionPreset = "standard" | "light";

export interface CreateCollectionRequest {
  name: string;
  supported_formats: string[];
  max_file_size_bytes: number;
  /** `null`/omitted inherits the worker's global default job timeout. */
  job_timeout_seconds?: number | null;
  fields: FieldSpec[];
  pipeline?: Record<string, unknown> | null;
  /** Stock-blob selector (ignored when `pipeline` is set): "light" = fast, enrichment-free core. */
  preset?: CollectionPreset | null;
}

/**
 * Patch payload — every field optional, mirroring the backend's diff semantics: `fields` is the
 * FULL target schema (fields omitted from the list are removed, together with their stored
 * values); a searchable-surface change flips `needs_reindex` on the returned Collection.
 */
export interface UpdateCollectionRequest {
  name?: string | null;
  supported_formats?: string[] | null;
  max_file_size_bytes?: number | null;
  /** `null` reverts to inheriting the worker's global default job timeout. */
  job_timeout_seconds?: number | null;
  fields?: FieldSpec[] | null;
  pipeline?: Record<string, unknown> | null;
  search?: Record<string, unknown> | null;
  note?: string | null;
}

export function listCollections(): Promise<Collection[]> {
  return apiFetch(BASE);
}

export function getCollection(id: string): Promise<Collection> {
  return apiFetch(`${BASE}/${id}`);
}

export function createCollection(request: CreateCollectionRequest): Promise<Collection> {
  return apiFetch(BASE, jsonInit("POST", request));
}

export function updateCollection(id: string, request: UpdateCollectionRequest): Promise<Collection> {
  return apiFetch(`${BASE}/${id}`, jsonInit("PATCH", request));
}

export function deleteCollection(id: string): Promise<void> {
  return apiFetch(`${BASE}/${id}`, { method: "DELETE" });
}

/** Mirrors a node card's `config_schema` face — see `GET /collections/contract-schema`. */
interface CollectionContractSchemaResponse {
  config_schema: JsonSchema;
}

/**
 * Discover the collection identity/limits contract as JSON Schema — fed straight into the
 * shared `SchemaForm`, exactly like a node's `config_schema`, so a new backend contract field
 * auto-surfaces in the wizard with zero further frontend edit.
 */
export async function fetchCollectionContractSchema(): Promise<JsonSchema> {
  const response = await apiFetch<CollectionContractSchemaResponse>(`${BASE}/contract-schema`);
  return response.config_schema;
}

// ====== Collection operational health (on-demand provider reachability probe) ======
// Mirrors GET /api/v1/collections/{id}/health — a read-only sweep, zero spend, zero mutation.

/** One provider-hosted action leaf's reachability outcome. */
export type ProviderStatus = "ok" | "unreachable" | "auth_failed" | "not_configured" | "skipped";

/** Side of the graph a probed provider node belongs to. */
export type ProviderSide = "ingest" | "search";

export interface ProviderHealth {
  node_id: string;
  kind: string;
  family: string;
  side: ProviderSide;
  status: ProviderStatus;
  /** Secret-free base URL the provider was probed at. `null` when the node has no endpoint concept
   *  (a local/in-process step); `""` when the node inherits its endpoint from elsewhere in the graph. */
  endpoint: string | null;
  detail: string | null;
  latency_ms: number | null;
}

export interface IngestHealth {
  buildable: boolean;
  build_error: string | null;
  providers: ProviderHealth[];
}

export interface SearchIndexHealth {
  vector_count: number;
  last_ingest_at: string | null;
}

/** `true` = fully operational, `false` = unavailable, `"degraded"` = answers but impaired. */
export type SearchOperational = true | false | "degraded";

export interface SearchHealth {
  buildable: boolean;
  search_operational: SearchOperational;
  build_error: string | null;
  providers: ProviderHealth[];
  index: SearchIndexHealth;
}

/** Mirrors the backend's `HealthVerdict` StrEnum — five honest states, not a binary up/down.
 *  `empty` is NEUTRAL (nothing indexed yet, not a fault); `ingest_unavailable` means new documents
 *  cannot be ingested while an existing index may still be searchable (not a global outage). */
export type HealthVerdictValue = "operational" | "empty" | "degraded" | "ingest_unavailable" | "down";

export interface CollectionHealth {
  collection_id: string;
  verdict: HealthVerdictValue;
  /** A human-readable, jargon-free first line explaining the verdict — the ONLY text the UI should
   *  show as the headline detail; raw engine errors stay in `ingest.build_error`/`search.build_error`. */
  reason: string;
  checked_at: string;
  ingest: IngestHealth;
  search: SearchHealth;
}

/** Runs the on-demand provider reachability sweep — no job enqueued, no DB/S3 write. */
export function getCollectionHealth(id: string): Promise<CollectionHealth> {
  return apiFetch(`${BASE}/${id}/health`);
}

// ====== Collection storage footprint (per-store byte accounting) ======
// Mirrors GET /api/v1/collections/{id}/storage — a read-only accounting sweep across the three
// physical stores a collection touches. `estimated` on postgres/qdrant flags a sampled/approximated
// number (row-size heuristics, no exact SELECT pg_total_relation_size per collection); s3 is exact
// (content-addressed object sizes).

/** S3 object storage for a collection or a single document — `physical_unique_bytes` can be lower
 *  than `total_bytes` when content-addressing dedupes identical blobs across documents. */
export interface StorageS3Stats {
  original_bytes: number;
  rendered_bytes: number;
  total_bytes: number;
  physical_unique_bytes: number;
  estimated: boolean;
}

/** Postgres row storage for a collection or a single document, broken down by table family. */
export interface StoragePostgresStats {
  documents_bytes: number;
  ir_blocks_bytes: number;
  enrichment_bytes: number;
  chunks_bytes: number;
  metadata_bytes: number;
  observability_bytes: number;
  total_bytes: number;
  estimated: boolean;
}

/** Qdrant vector storage for a collection or a single document. */
export interface StorageQdrantStats {
  points: number;
  dense_bytes: number;
  sparse_bytes: number;
  payload_bytes: number;
  total_bytes: number;
  estimated: boolean;
}

/** One document's slice of the collection's storage footprint. */
export interface DocumentStorageBreakdown {
  document_id: string;
  filename: string;
  s3: StorageS3Stats;
  postgres: StoragePostgresStats;
  qdrant: StorageQdrantStats;
  total_bytes: number;
}

/** Full per-collection storage footprint — the three stores plus a per-document breakdown, already
 *  sorted descending by `total_bytes`. */
export interface CollectionStorage {
  collection_id: string;
  s3: StorageS3Stats;
  postgres: StoragePostgresStats;
  qdrant: StorageQdrantStats;
  grand_total_bytes: number;
  documents: DocumentStorageBreakdown[];
}

/** Runs the storage accounting sweep — read-only, no job enqueued. */
export function fetchCollectionStorage(id: string): Promise<CollectionStorage> {
  return apiFetch(`${BASE}/${id}/storage`);
}

// ====== Mass re-ingestion (whole collection or a document subset) ======
// Mirrors POST /api/v1/collections/{id}/reingest — always a FULL-pipeline re-run per document
// (no partial/stage-scoped re-run exists). Omitting `document_ids` targets the whole collection.

/** `document_ids` omitted/null re-ingests the WHOLE collection; `[]` is rejected (422) by the API. */
export interface ReingestRequest {
  document_ids?: string[] | null;
}

/** One document's freshly-enqueued re-ingest job. */
export interface ReingestJobHandle {
  document_id: string;
  job_id: string;
}

export interface ReingestResponse {
  collection_id: string;
  count: number;
  jobs: ReingestJobHandle[];
}

/**
 * Re-run the FULL ingestion pipeline on every stored original in `documentIds`, or the whole
 * collection when omitted. Idempotent per document (previous chunks/IR/pages purged, vectors
 * overwritten) — each targeted document gets its own queued job.
 */
export function reingestCollection(id: string, documentIds?: string[]): Promise<ReingestResponse> {
  const request: ReingestRequest = { document_ids: documentIds ?? null };
  return apiFetch(`${BASE}/${id}/reingest`, jsonInit("POST", request));
}

// ====== Cost/volume dry-run estimate (read-only pipeline pricing preview) ======
// Mirrors POST /api/v1/collections/{id}/estimate — a read-only sweep across the collection's
// configured pipeline. Never enqueues a job and never spends against a provider.

/** "pending" (default) scopes the sweep to not-yet-ingested documents; "all" re-projects the whole collection. */
export type EstimateScope = "pending" | "all";

export interface EstimateRequest {
  scope?: EstimateScope;
}

/**
 * One pipeline stage's projected usage and price. `cost_usd`/`rate_known` are `null`/`false` when
 * the stage's provider has no configured rate card — that is distinct from a genuinely free stage,
 * which reports `cost_usd: 0` with `rate_known: true`.
 */
export interface CostEstimateStage {
  stage: string;
  family: string;
  provider: string;
  model: string | null;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  pages: number;
  cost_usd: number | null;
  rate_known: boolean;
}

/** Projected ingest output volume — independent of pricing, always known even for an unpriced pipeline. */
export interface CostEstimateVolume {
  pages: number;
  chunks: number;
  dense_vectors: number;
  sparse_vectors: number;
  storage_bytes: number;
}

/**
 * Full dry-run estimate for a collection. `total_cost_usd` is `null` only when NO stage is
 * priceable at all (never conflated with `0.0`, which means an actually-free/parse-only
 * pipeline); `cost_complete` is `false` whenever at least one priced stage's provider has no
 * known rate, so the total understates the real spend.
 */
export interface CostEstimate {
  document_count: number;
  stages: CostEstimateStage[];
  volume: CostEstimateVolume;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost_usd: number | null;
  cost_complete: boolean;
  assumptions: Record<string, unknown>;
  caveats: string[];
}

/** Runs the dry-run cost/volume estimate — read-only, no job enqueued, no provider spend. */
export function estimateCollectionCost(id: string, scope: EstimateScope = "pending"): Promise<CostEstimate> {
  const request: EstimateRequest = { scope };
  return apiFetch(`${BASE}/${id}/estimate`, jsonInit("POST", request));
}
