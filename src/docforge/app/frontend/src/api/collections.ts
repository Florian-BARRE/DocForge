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

export type HealthVerdictValue = "operational" | "degraded" | "down";

export interface CollectionHealth {
  collection_id: string;
  verdict: HealthVerdictValue;
  checked_at: string;
  ingest: IngestHealth;
  search: SearchHealth;
}

/** Runs the on-demand provider reachability sweep — no job enqueued, no DB/S3 write. */
export function getCollectionHealth(id: string): Promise<CollectionHealth> {
  return apiFetch(`${BASE}/${id}/health`);
}
