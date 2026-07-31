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

export interface SearchHitModel {
  chunk_id: string;
  document_id: string;
  score: number;
  text: string;
  chunk_index: number;
  token_count: number;
}

export interface SearchResponse {
  query: string;
  hits: SearchHitModel[];
  debug_info: Record<string, unknown> | null;
}

export function search(collectionId: string, request: SearchRequest): Promise<SearchResponse> {
  return apiFetch(`${BASE}/${collectionId}/search`, jsonInit("POST", request));
}
