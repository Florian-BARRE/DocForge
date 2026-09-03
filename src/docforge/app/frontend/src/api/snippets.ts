// ====== Code Summary ======
// TypeScript mirror of the granular collection config-SNIPPET REST contract + its typed client.
// Shapes copied verbatim from the backend's Pydantic models (app/backend/routers/snippets/models.py)
// — nothing invented. Distinct from api/transfers.ts's whole-collection `.dcexport` bundle: a
// snippet is SYNCHRONOUS and config-only (one slice — pipeline / search / schema), so both calls
// here are plain request/response, no polling.

import { apiFetch, jsonInit } from "./http";

const COLLECTIONS_BASE = "/api/v1/collections";

/** The three config slices a snippet can carry. */
export type SnippetKind = "pipeline" | "search" | "schema";

/** File extension the frontend saves a snippet under — deliberately distinct from `.dcexport`. */
export const SNIPPET_FILE_EXTENSION = ".dfsnippet";

/** A portable, secret-masked, versioned wrapper around one collection-config slice. */
export interface CollectionSnippet {
  kind: SnippetKind;
  format_version: number;
  docforge_version: string;
  /** The slice payload: the graph blob for `pipeline`/`search`, or `{fields: [...]}` for `schema`. */
  body: Record<string, unknown>;
}

export interface SnippetImportResult {
  collection_id: string;
  kind: SnippetKind;
  /** Whether applying this snippet flags a reindex requirement — always false for a search snippet. */
  needs_reindex: boolean;
}

/** Export one config slice of a collection as a versioned, secret-masked snippet — synchronous. */
export function getSnippet(collectionId: string, kind: SnippetKind): Promise<CollectionSnippet> {
  return apiFetch(`${COLLECTIONS_BASE}/${collectionId}/snippets/${kind}`);
}

/**
 * Apply an inbound config snippet onto an existing collection — synchronous, config-only.
 *
 * 422s when the snippet's `format_version` is unsupported or its `kind` doesn't match `kind`.
 */
export function applySnippet(collectionId: string, kind: SnippetKind, snippet: CollectionSnippet): Promise<SnippetImportResult> {
  return apiFetch(`${COLLECTIONS_BASE}/${collectionId}/snippets/${kind}`, jsonInit("POST", snippet));
}
