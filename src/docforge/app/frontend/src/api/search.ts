// ====== Code Summary ======
// TypeScript mirror of the collection search REST contract + its typed client. Shapes copied
// verbatim from the backend's SearchRequest/SearchResponse Pydantic models — nothing invented.

import { apiFetch, HttpError, jsonInit } from "./http";

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
  /** Null for a page-less document (no page render) — caught missing by `_contractParity.ts`, 2026-09. */
  page: number | null;
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

// ====== Honest search-failure classification ======
// The search router now distinguishes a PERMANENT config/auth fault from a genuinely TRANSIENT
// overload/timeout (see backend/routers/search/helpers.py::encode_failure_http) instead of a
// blanket "the embedder is busy, retry shortly". Classify the caught error the same way here so the
// UI never tells a caller to retry a dead endpoint.

export type SearchErrorKind = "config" | "overloaded" | "timeout" | "generic";

export interface SearchErrorInfo {
  kind: SearchErrorKind;
  message: string;
}

/** 424 codes naming a permanent provider config/auth fault — never a transient one. */
const CONFIG_ERROR_MESSAGES: Record<string, string> = {
  embedder_unreachable: "Search unavailable — the collection's embedder is unreachable. Fix its provider config.",
  embedder_auth_failed: "Search unavailable — the collection's embedder rejected its credentials. Fix its provider config.",
};

/**
 * Classify a failed `search()` call into a UI-facing kind + message.
 *
 * A 424 `embedder_unreachable`/`embedder_auth_failed` is a permanent config fault (never "retry
 * shortly"); a 503 `embedder_overloaded` or any other 503 is a genuine transient overload; a 504
 * `search_timeout` (or any 504) is a timeout; anything else falls back to the raw error message.
 *
 * @param error - Whatever the `search()` promise rejected with.
 * @returns The classified kind and a human-readable message to render.
 */
export function classifySearchError(error: unknown): SearchErrorInfo {
  if (error instanceof HttpError) {
    const code = error.issues[0]?.code;
    if (code && code in CONFIG_ERROR_MESSAGES) {
      return { kind: "config", message: CONFIG_ERROR_MESSAGES[code] };
    }
    if (code === "embedder_overloaded" || error.status === 503) {
      return { kind: "overloaded", message: "Search is temporarily degraded — the embedder is overloaded. Retry shortly." };
    }
    if (code === "search_timeout" || error.status === 504) {
      return { kind: "timeout", message: "Search timed out — the run took too long. Retry." };
    }
    return { kind: "generic", message: error.message };
  }
  return { kind: "generic", message: error instanceof Error ? error.message : String(error) };
}
