// ====== Code Summary ======
// TypeScript mirror of the collection-ALIAS REST contract + its typed client. Shapes copied verbatim
// from the backend's Pydantic models (app/backend/routers/collection_aliases/models.py). An alias is a
// stable name usable in place of a collection UUID (and as an `alias:<name>` key scope); re-pointing it
// is the blue/green switch.

import { apiFetch, jsonInit } from "./http";

const BASE = "/api/v1/collection-aliases";

/** The key-scope entry prefix binding a key to an alias's CURRENT target. */
export const ALIAS_SCOPE_PREFIX = "alias:";

export interface CollectionAlias {
  /** The alias name (a slug: lowercase, digits, '-', '_'). */
  name: string;
  collection_id: string;
  collection_name: string;
  created_at: string;
  /** When the alias was last (re-)pointed. */
  updated_at: string;
}

export interface SetCollectionAliasResponse extends CollectionAlias {
  /** True when this call created the alias. */
  created: boolean;
  /** Where the alias pointed before (null = just created; equal to collection_id = no-op). */
  previous_collection_id?: string | null;
}

/** Every alias with its current target. */
export function listCollectionAliases(): Promise<CollectionAlias[]> {
  return apiFetch(BASE);
}

/** Create the alias, or atomically re-point it, at `collectionId`. */
export function setCollectionAlias(name: string, collectionId: string): Promise<SetCollectionAliasResponse> {
  return apiFetch(`${BASE}/${encodeURIComponent(name)}`, jsonInit("PUT", { collection_id: collectionId }));
}
