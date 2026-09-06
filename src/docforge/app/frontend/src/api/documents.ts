// ====== Code Summary ======
// TypeScript mirror of the documents upload contract + its typed client (multipart/form-data).

import { apiFetch, jsonInit } from "./http";

const BASE = "/api/v1/documents";

export interface UploadAccepted {
  document_id: string;
  job_id: string;
  duplicate: boolean;
}

export interface UploadDocumentArgs {
  file: File;
  collectionId: string;
  metadata: Record<string, unknown>;
}

/** The desired searchability state for a document (the reversible toggle). */
export interface EnabledPatch {
  enabled: boolean;
}

/** A document's searchability state after toggling it. */
export interface DocumentEnabledResponse {
  document_id: string;
  enabled: boolean;
}

export function uploadDocument({ file, collectionId, metadata }: UploadDocumentArgs): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file);
  form.append("collection_id", collectionId);
  form.append("metadata", JSON.stringify(metadata));
  return apiFetch(BASE, { method: "POST", body: form });
}

/** Toggle a document's searchability — reversible, no re-ingest (a single Postgres flag). */
export function setDocumentEnabled(id: string, enabled: boolean): Promise<DocumentEnabledResponse> {
  return apiFetch(`${BASE}/${id}/enabled`, jsonInit("PATCH", { enabled }));
}

/** Options for {@link reingestDocument}. */
export interface ReingestOptions {
  /** Bypass the stage cache and recompute every stage from scratch — mirrors the backend's own
   *  `force` query flag (default false). Use to rebuild after a code change that didn't bump a
   *  node's CACHE_VERSION. */
  force?: boolean;
}

/** Re-run ingestion on the document's stored original — no re-upload — with the collection's current
 *  pipeline. Idempotent (previous chunks/IR/pages purged, vectors overwritten). Returns the new job.
 *  Throws `HttpError` 409 when a run is already active for this document. */
export function reingestDocument(id: string, options: ReingestOptions = {}): Promise<UploadAccepted> {
  const query = options.force ? "?force=true" : "";
  return apiFetch(`${BASE}/${id}/reingest${query}`, { method: "POST" });
}
