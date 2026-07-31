// ====== Code Summary ======
// TypeScript mirror of the collection search REST contract + its typed client. Shapes copied
// verbatim from the backend's SearchRequest/SearchResponse Pydantic models — nothing invented.

import { apiFetch, jsonInit } from "./http";

const BASE = "/api/v1/collections";

export interface SearchTargetModel {
  field: string;
  semantic: boolean;
  lexical: boolean;
}

export interface SearchRequest {
  query: string;
  limit?: number | null;
  filters?: Record<string, unknown> | null;
  search_in?: SearchTargetModel[] | null;
}

/** One source block's location on the page — page + NORMALISED [0,1] bbox — enough to draw a box. */
export interface BlockLocationModel {
  page: number;
  /** Bounding box [x0, y0, x1, y1] normalised to [0, 1]. */
  bbox: number[];
}

export interface SearchHitModel {
  chunk_id: string;
  document_id: string;
  filename?: string | null;
  document_title?: string | null;
  heading_path?: string[];
  metadata?: Record<string, unknown>;
  score: number;
  text: string;
  chunk_index: number;
  token_count: number;
  /** IR block ids the chunk was assembled from (assembly order). */
  block_ids?: string[];
  /** Page of the chunk's primary (leading) block — where to draw the box. Null when unlocated. */
  page?: number | null;
  /** The primary block's NORMALISED [0, 1] bounding box. Null when unlocated. */
  bbox?: number[] | null;
  /** Every source block's page + NORMALISED bbox — draw one box per block. */
  block_locations?: BlockLocationModel[];
}

export interface SearchResponse {
  query: string;
  hits: SearchHitModel[];
  debug_info: Record<string, unknown> | null;
}

export function search(collectionId: string, request: SearchRequest): Promise<SearchResponse> {
  return apiFetch(`${BASE}/${collectionId}/search`, jsonInit("POST", request));
}
