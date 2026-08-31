// ====== Code Summary ======
// TypeScript mirror of the corpus grid REST contract (POST /documents/query + the three bulk-op
// endpoints) + its typed client. Shapes copied verbatim from the backend's Pydantic models (see
// /openapi.json) — nothing invented. Kept separate from api/explorer.ts (single-document reads)
// and api/collections.ts (whole-collection reingest) since this is a distinct, grid-shaped surface.

import type { DocumentStatus } from "./explorer";
import { apiFetch, jsonInit } from "./http";

export type { DocumentStatus } from "./explorer";

const BASE = "/api/v1/collections";

/** A string-column predicate — case-insensitive substring and/or exact match (AND-combined). */
export interface TextFilter {
  contains?: string | null;
  eq?: string | null;
}

/** An inclusive numeric range predicate (either bound may be omitted). */
export interface NumberRange {
  gte?: number | null;
  lte?: number | null;
}

/** An inclusive ISO-datetime range predicate (either bound may be omitted). */
export interface DateRange {
  gte?: string | null;
  lte?: string | null;
}

export type MetadataFilterOp = "eq" | "contains" | "in" | "gte" | "lte";

/** One dynamic document-metadata predicate, addressed by field name. */
export interface MetadataFilter {
  field: string;
  op: MetadataFilterOp;
  value: unknown;
}

/** The per-column filter for one query — every clause is optional and AND-combined. An empty
 *  filter (all clauses omitted) matches the whole collection. */
export interface DocumentFilter {
  filename?: TextFilter | null;
  title?: TextFilter | null;
  status?: DocumentStatus[] | null;
  format?: string[] | null;
  language?: string[] | null;
  file_size?: NumberRange | null;
  page_count?: NumberRange | null;
  created_at?: DateRange | null;
  enabled?: boolean | null;
  metadata?: MetadataFilter[];
}

/** The single sort key — a base column or a document-metadata field name; the server appends
 *  `id` as the stable secondary key so offset paging never skips or duplicates a row. */
export interface DocumentSort {
  field: string;
  direction: "asc" | "desc";
}

export interface Pagination {
  limit: number;
  offset: number;
}

/** The full grid query — filter + sort + pagination (all optional). */
export interface DocumentQueryRequest {
  filter?: DocumentFilter | null;
  sort?: DocumentSort | null;
  pagination: Pagination;
}

/** One grid row — the base catalogue fields plus a compact document-metadata value map. */
export interface DocumentGridRow {
  id: string;
  filename: string;
  format: string;
  status: DocumentStatus;
  page_count: number | null;
  file_size: number;
  created_at: string | null;
  title: string;
  language: string | null;
  enabled: boolean;
  metadata: Record<string, unknown>;
}

export interface DocumentQueryResponse {
  total: number;
  limit: number;
  offset: number;
  rows: DocumentGridRow[];
}

/** The shared bulk-op target: an explicit id set XOR a filter (minus a few deselected ids).
 *  Exactly one mode is allowed — id mode (`document_ids`) or filter mode (`filter` +
 *  optional `exclude_ids`, the "select-all-minus-N" the grid needs at 100k scale). */
export type DocumentSelector =
  | { document_ids: string[]; filter?: never; exclude_ids?: never }
  | { filter: DocumentFilter; exclude_ids?: string[]; document_ids?: never };

export interface BulkDeleteResponse {
  collection_id: string;
  matched: number;
  deleted: number;
}

export interface BulkEnabledResponse {
  collection_id: string;
  enabled: boolean;
  matched: number;
  updated: number;
  reindex_implied: boolean;
}

export interface ReingestJobHandle {
  document_id: string;
  job_id: string;
}

export interface BulkReingestResponse {
  collection_id: string;
  matched: number;
  enqueued: number;
  capped: boolean;
  max_fanout: number;
  jobs: ReingestJobHandle[];
}

/** One filtered/sorted/paginated page of a collection's documents + the total match count. */
export function queryDocuments(collectionId: string, request: DocumentQueryRequest): Promise<DocumentQueryResponse> {
  return apiFetch(`${BASE}/${collectionId}/documents/query`, jsonInit("POST", request));
}

/** Delete every selected document everywhere (Qdrant points + PG cascade + orphan-only blob purge). */
export function bulkDeleteDocuments(collectionId: string, selector: DocumentSelector): Promise<BulkDeleteResponse> {
  return apiFetch(`${BASE}/${collectionId}/documents/delete`, jsonInit("POST", selector));
}

/** Enable or disable every selected document — a pure Postgres flag flip (no re-index, no Qdrant). */
export function bulkSetDocumentsEnabled(
  collectionId: string,
  enabled: boolean,
  selector: DocumentSelector,
): Promise<BulkEnabledResponse> {
  return apiFetch(`${BASE}/${collectionId}/documents/set-enabled?enabled=${enabled}`, jsonInit("POST", selector));
}

/** Re-run the full pipeline over every selected document — one fresh job per document. A filter
 *  selector matching more than the server's fan-out ceiling enqueues only the first N and reports
 *  `capped=true` with the full `matched` count. */
export function bulkReingestDocuments(collectionId: string, selector: DocumentSelector): Promise<BulkReingestResponse> {
  return apiFetch(`${BASE}/${collectionId}/documents/reingest`, jsonInit("POST", selector));
}
