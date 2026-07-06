// ====== Code Summary ======
// TypeScript mirror of the document explorer REST contract (catalogue, facts/metadata, pages,
// IR, chunks, blobs) + its typed client. Shapes copied verbatim from the backend's Pydantic
// models (see /openapi.json) — nothing invented.

import type { FieldOrigin } from "./collections";
import { apiFetch } from "./http";

const DOCUMENTS_BASE = "/api/v1/documents";
const COLLECTIONS_BASE = "/api/v1/collections";
const BLOBS_BASE = "/api/v1/blobs";

export type DocumentStatus = "pending" | "processing" | "done" | "failed";
export type SourceKind = "digital_born" | "scanned" | "mixed";
export type EnrichmentKind = "classify" | "ocr" | "vlm" | "chart_to_data" | "table_summary";
export type EnrichmentStatus = "ok" | "failed" | "skipped";

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
  column_index: number;
  parent_id: string | null;
  level: number | null;
  text: string | null;
  is_boilerplate: boolean;
  language: string | null;
  confidence: number | null;
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

export function getDocumentChunks(id: string): Promise<ChunkInfo[]> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}/chunks`);
}

export function deleteDocument(id: string): Promise<void> {
  return apiFetch(`${DOCUMENTS_BASE}/${id}`, { method: "DELETE" });
}

/** Direct blob URL — used verbatim as an `<img src>` or a canonical-PDF link. */
export function blobUrl(hash: string): string {
  return `${BLOBS_BASE}/${hash}`;
}
