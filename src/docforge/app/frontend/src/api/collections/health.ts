// ====== Code Summary ======
// Collection operational health (on-demand provider reachability probe) and storage footprint
// (per-store byte accounting) — both read-only sweeps.

import { apiFetch } from "../http";
import { COLLECTIONS_BASE as BASE } from "./base";

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
  /** This document's share of the heavy full execution-trace payloads (see
   *  {@link CollectionStorage.trace_bytes}) — already folded into `total_bytes`. */
  trace_bytes: number;
  total_bytes: number;
}

/** Full per-collection storage footprint — the three stores plus a per-document breakdown, already
 *  sorted descending by `total_bytes`. */
export interface CollectionStorage {
  collection_id: string;
  s3: StorageS3Stats;
  postgres: StoragePostgresStats;
  qdrant: StorageQdrantStats;
  /** Heavy full execution-trace payloads stored in S3 under `trace/{job_id}/` (opt-in
   *  `trace_verbosity='full'` tier) — reclaimable via {@link purgeCollectionTracePayloads}. Already
   *  folded into `grand_total_bytes`, not part of `s3`. */
  trace_bytes: number;
  grand_total_bytes: number;
  documents: DocumentStorageBreakdown[];
}

/** Runs the storage accounting sweep — read-only, no job enqueued. */
export function fetchCollectionStorage(id: string): Promise<CollectionStorage> {
  return apiFetch(`${BASE}/${id}/storage`);
}
