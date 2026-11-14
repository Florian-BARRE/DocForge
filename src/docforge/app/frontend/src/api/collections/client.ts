// ====== Code Summary ======
// Typed client of the collections REST resource: CRUD, index rebuild, mass re-ingestion and the
// trace-payload purge.

import { apiFetch, jsonInit } from "../http";
import { COLLECTIONS_BASE as BASE } from "./base";
import type { Collection, CreateCollectionRequest, UpdateCollectionRequest, UpdateCollectionResponse } from "./types";

export function listCollections(): Promise<Collection[]> {
  return apiFetch(BASE);
}

export function getCollection(id: string): Promise<Collection> {
  return apiFetch(`${BASE}/${id}`);
}

export function createCollection(request: CreateCollectionRequest): Promise<Collection> {
  return apiFetch(BASE, jsonInit("POST", request));
}

export function updateCollection(id: string, request: UpdateCollectionRequest): Promise<UpdateCollectionResponse> {
  return apiFetch(`${BASE}/${id}`, jsonInit("PATCH", request));
}

export function deleteCollection(id: string): Promise<void> {
  return apiFetch(`${BASE}/${id}`, { method: "DELETE" });
}

/** The tracked `rebuild_index` job started by `POST /collections/{id}/rebuild-index` (202). */
export interface RebuildIndexAccepted {
  collection_id: string;
  job_id: string;
}

/** Rebuilds the vector index from the current schema/embedder — no content re-embed of documents. */
export function rebuildCollectionIndex(id: string): Promise<RebuildIndexAccepted> {
  return apiFetch(`${BASE}/${id}/rebuild-index`, { method: "POST" });
}

// ====== Mass re-ingestion (whole collection or a document subset) ======
// Mirrors POST /api/v1/collections/{id}/reingest — a full-pipeline re-run per document by default
// (or a stage replay via `replay_from`). Omitting `document_ids` targets the whole collection.

/** `document_ids` omitted/null re-ingests the WHOLE collection; `[]` is rejected (422) by the API. */
export interface ReingestRequest {
  document_ids?: string[] | null;
  /** Replay from this post-IR stage (no re-parse); omit/null = full re-run. */
  replay_from?: string | null;
  /** Acknowledge the estimate of a reingest above the server's confirm threshold. */
  confirm_estimate?: boolean;
}

/** One document's freshly-enqueued re-ingest job. */
export interface ReingestJobHandle {
  document_id: string;
  job_id: string;
}

export interface ReingestResponse {
  collection_id: string;
  count: number;
  /** Documents skipped because a run was already active for them (the per-document active-job lock). */
  skipped_in_flight: number;
  skipped_not_replayable?: number;
  jobs: ReingestJobHandle[];
}

/**
 * Re-run the FULL ingestion pipeline on every stored original in `documentIds`, or the whole
 * collection when omitted. Idempotent per document (previous chunks/IR/pages purged, vectors
 * overwritten) — each targeted document gets its own queued job.
 */
export function reingestCollection(
  id: string,
  documentIds?: string[],
  options: { replayFrom?: string | null; confirmEstimate?: boolean } = {},
): Promise<ReingestResponse> {
  const request: ReingestRequest = {
    document_ids: documentIds ?? null,
    replay_from: options.replayFrom ?? null,
    confirm_estimate: options.confirmEstimate ?? false,
  };
  return apiFetch(`${BASE}/${id}/reingest`, jsonInit("POST", request));
}

// ====== Trace-payload purge (reclaim the heavy opt-in `trace_verbosity='full'` object-store bytes) ======
// Mirrors POST /api/v1/collections/{id}/trace-payloads/purge (collection scope) and the document-scoped
// analogue at POST /api/v1/documents/{id}/trace-payloads/purge (see api/documents.ts). Idempotent
// (nothing stored -> zeros) and best-effort (never 500s on a partial storage failure).

/** The outcome of a trace-payload purge, collection- or document-scoped — same shape either way. */
export interface TracePurgeResult {
  purged_jobs: number;
  deleted_objects: number;
}

/** Reclaims every stored full execution-trace payload across the collection's jobs. */
export function purgeCollectionTracePayloads(id: string): Promise<TracePurgeResult> {
  return apiFetch(`${BASE}/${id}/trace-payloads/purge`, { method: "POST" });
}
