// ====== Code Summary ======
// TypeScript mirror of the document explorer REST contract (catalogue, facts/metadata, pages,
// IR, chunks, blobs) + its typed client. Shapes copied verbatim from the backend's Pydantic
// models (see /openapi.json) — nothing invented.

import type { FieldOrigin } from "./collections";
import { apiFetch, apiFetchBlob, jsonInit } from "./http";
import type { JobEvent } from "./jobs";

const DOCUMENTS_BASE = "/api/v1/documents";
const COLLECTIONS_BASE = "/api/v1/collections";
const BLOBS_BASE = "/api/v1/blobs";
const CHUNKS_BASE = "/api/v1/chunks";

export type DocumentStatus = "pending" | "processing" | "done" | "failed" | "cancelled";
export type SourceKind = "digital_born" | "scanned" | "mixed";
export type EnrichmentKind = "classify" | "ocr" | "vlm" | "chart_to_data" | "table_summary";
export type EnrichmentStatus = "ok" | "failed" | "skipped";

/**
 * A chunk's structural classification, assigned by the pipeline (not a user choice). Drives the
 * default effective-enabled state: only `body` is searchable by default — every other role
 * defaults off and needs an explicit enable to become searchable.
 */
export type ChunkRole = "body" | "header_footer" | "toc" | "boilerplate";

/** One row of a collection's document catalogue (the browse list). */
export interface DocumentListItem {
  id: string;
  filename: string;
  format: string;
  status: DocumentStatus;
  page_count: number | null;
  file_size: number;
  created_at: string | null;
  title: string;
  language: string | null;
  /** The document-level searchability toggle — disabling hides every chunk regardless of role. */
  enabled: boolean;
}

/** One resolved metadata value — the schema field name, its stored value, and who filled it. */
export interface MetadataValue {
  field_name: string;
  value: unknown;
  origin: FieldOrigin;
}

/** A document's full facts plus its resolved document-level metadata. */
export interface DocumentDetail {
  id: string;
  collection_id: string;
  filename: string;
  format: string;
  mime_type: string;
  file_size: number;
  page_count: number | null;
  language: string | null;
  title: string;
  source_kind: SourceKind;
  status: DocumentStatus;
  source_hash: string;
  pdf_blob_hash: string | null;
  simhash: string | null;
  pipeline_version: string;
  created_at: string | null;
  metadata: MetadataValue[];
  /** The document-level searchability toggle — disabling hides every chunk regardless of role. */
  enabled: boolean;
}

/** One page's geometry, routing and its render blob reference. */
export interface PageInfo {
  page_number: number;
  width: number | null;
  height: number | null;
  is_scanned: boolean;
  language: string | null;
  render_blob_hash: string | null;
}

/** One raw IR block — structure, position in reading order and native text. */
export interface IRBlock {
  id: string;
  block_type: string;
  page: number;
  bbox: number[];
  reading_order: number;
  parent_id: string | null;
  level: number | null;
  text: string | null;
  is_boilerplate: boolean;
  language: string | null;
}

/** A TABLE block's parsed structure (1:1 with its block). */
export interface IRTable {
  block_id: string;
  n_rows: number;
  n_cols: number;
  has_header: boolean;
  /** Row-major 2D cell grid — untyped on the wire (JSON), narrowed defensively when rendered. */
  cells: unknown;
  linearized_md: string | null;
}

/** A FIGURE block's parse-time facts (1:1 with its block). */
export interface IRFigure {
  block_id: string;
  crop_blob_hash: string | null;
  caption_block_id: string | null;
}

/** One enrichment applied to a block (OCR/VLM/classify/chart_to_data/table_summary). */
export interface IREnrichment {
  id: string;
  block_id: string;
  kind: EnrichmentKind;
  text: string | null;
  data: unknown;
  status: EnrichmentStatus;
}

/** The full IR of a document — raw blocks, table/figure details and every enrichment. */
export interface DocumentIR {
  blocks: IRBlock[];
  tables: IRTable[];
  figures: IRFigure[];
  enrichments: IREnrichment[];
}

/** One retrieval chunk — enriched text, composition (block ids) and generated metadata. */
export interface ChunkInfo {
  id: string;
  chunk_index: number;
  text: string;
  token_count: number;
  is_indexed: boolean;
  strategy: string;
  parent_id: string | null;
  block_ids: string[];
  metadata: MetadataValue[];
  /** Structural classification assigned by the pipeline — drives the default enabled state. */
  role: ChunkRole;
  /** The recomputed EFFECTIVE searchability state (enabled_override ?? role_default_enabled). */
  enabled: boolean;
  /** The chunk's section breadcrumb (outer→inner headings); [] when none. */
  heading_path: string[];
  /** Page of the chunk's primary (leading) block; null when it has no located block. */
  page: number | null;
}

/** The desired searchability state for one chunk (its enabled_override). */
export interface ChunkEnabledPatch {
  enabled: boolean;
}

/**
 * The outcome of toggling one chunk's searchability.
 *
 * `reindex_required` is true only when enabling a chunk that was never embedded — it has no
 * Qdrant point, so it is NOT searchable until a later on-demand re-embed runs.
 *
 * `search_sync_pending`/`search_sync_error` (caught missing by `_contractParity.ts`, 2026-09):
 * meaningful on the single-chunk route — a bulk response's per-result entries always report
 * `false` here, the REQUEST-level flag on `BulkChunkEnabledResponse` is authoritative for a batch.
 */
export interface ChunkEnabledResult {
  chunk_id: string;
  enabled: boolean;
  reindex_required: boolean;
  search_sync_pending: boolean;
  search_sync_error: string | null;
}

/** Toggle several chunks' searchability to the same state in one call (the UI's multi-select). */
export interface BulkChunkEnabledPatch {
  chunk_ids: string[];
  enabled: boolean;
}

/**
 * The per-chunk outcomes of a bulk toggle plus the ids that did not resolve to a chunk.
 *
 * `search_sync_pending`/`search_sync_error` (caught missing by `_contractParity.ts`, 2026-09):
 * true when Postgres committed every toggle but the Qdrant payload sync failed — the search store
 * is stale until a re-run/backfill reconciles it. This is the request-level truth for the whole
 * batch (never a false full-success); the same fields on each nested `ChunkEnabledResult` stay
 * `false`/`null`.
 */
export interface BulkChunkEnabledResponse {
  results: ChunkEnabledResult[];
  not_found: string[];
  search_sync_pending: boolean;
  search_sync_error: string | null;
}

export function listDocuments(collectionId: string): Promise<DocumentListItem[]> {
  return apiFetch(`${COLLECTIONS_BASE}/${collectionId}/documents`);
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}`);
}

export function getDocumentPages(id: string): Promise<PageInfo[]> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}/pages`);
}

export function getDocumentIR(id: string): Promise<DocumentIR> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}/ir`);
}

/** A document's ingestion provenance — the parser/model pipeline that produced its IR + chunks. */
export interface DocumentProvenance {
  document_id: string;
  pipeline_version: string;
  /** The last ingestion job id — null when it has expired/been reaped (stages then empty). */
  job_id: string | null;
  /** False when no ingestion job survives (its stage timeline could not be recovered). */
  available: boolean;
  /** The per-stage trace in execution order: which node/parser/model ran, timing, token/cost. */
  stages: JobEvent[];
}

export function getDocumentProvenance(id: string): Promise<DocumentProvenance> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}/provenance`);
}

export function getDocumentChunks(id: string): Promise<ChunkInfo[]> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}/chunks`);
}

export function deleteDocument(id: string): Promise<void> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}`, { method: "DELETE" });
}

/** Toggle one chunk's searchability (reversible, no re-embed). */
export function setChunkEnabled(id: string, enabled: boolean): Promise<ChunkEnabledResult> {
  return apiFetch(`${CHUNKS_BASE}/${id}/enabled`, jsonInit("PATCH", { enabled }));
}

/** Toggle several chunks' searchability to the same state in one call (the multi-select bar). */
export function setChunksEnabled(chunkIds: string[], enabled: boolean): Promise<BulkChunkEnabledResponse> {
  return apiFetch(`${CHUNKS_BASE}/enabled`, jsonInit("PATCH", { chunk_ids: chunkIds, enabled }));
}

/** The blob route for a content hash. Fetch it through `apiFetchBlob` (bearer) — NOT as a raw
 *  `<img src>`/`<a href>`, which a browser navigation can't authenticate. See `components/BlobImage`. */
export function blobUrl(hash: string): string {
  return `${BLOBS_BASE}/${hash}`;
}

// ====== On-the-fly markdown/HTML views (generated from the canonical IR, never a stored blob) ======
// Mirrors GET /documents/{id}/markdown and /documents/{id}/html. Unlike blobUrl above, these are
// NOT content-hash routes — the body is rendered fresh from the document's IR on every request.

export type DocumentViewFormat = "markdown" | "html";

function documentViewUrl(id: string, format: DocumentViewFormat, download: boolean): string {
  return `${DOCUMENTS_BASE}/${id}/${format === "markdown" ? "markdown" : "html"}?download=${download}`;
}

/** The `<stem>.md`/`<stem>.html` filename the backend would attach — mirrored here so a caller can
 *  name the client-side download (Content-Disposition on a `fetch()`-constructed blob is not
 *  honoured by the browser; only a navigation respects it, so we must set it ourselves). */
export function documentViewFilename(filename: string, format: DocumentViewFormat): string {
  const stem = filename.replace(/\.[^./]+$/, "") || "document";
  return `${stem}.${format === "markdown" ? "md" : "html"}`;
}

/** Fetch a document's markdown/HTML view (authenticated) and open it inline in a new tab — mirrors
 *  `api/blobs.ts`'s `openBlobInNewTab`, generalized to a plain route instead of a content-hash one. */
export async function openDocumentViewInNewTab(id: string, format: DocumentViewFormat): Promise<void> {
  const blob = await apiFetchBlob(documentViewUrl(id, format, false));
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Fetch a document's markdown/HTML view (authenticated) and trigger a browser download under `filename`. */
export async function downloadDocumentView(id: string, format: DocumentViewFormat, filename: string): Promise<void> {
  const blob = await apiFetchBlob(documentViewUrl(id, format, true));
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
