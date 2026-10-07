// ====== Code Summary ======
// TypeScript mirror of the versioned collection config-HISTORY REST contract + its typed client.
// Shapes copied verbatim from the backend's Pydantic models
// (app/backend/routers/config_history/models.py); every config value served is secret-masked.

import { apiFetch } from "./http";

const COLLECTIONS_BASE = "/api/v1/collections";

/** One entry of a collection's config history (no config body). */
export interface ConfigVersionSummary {
  version: number;
  created_at: string;
  note?: string | null;
  /** Key name, "root", or "anonymous" (auth off); null = unknown / system write. */
  author_label?: string | null;
  author_key_id?: string | null;
  /** "pipeline:<node id>", "pipeline:(graph)", "search" — vs the previous version. */
  changes?: string[];
}

export interface ConfigVersionListResponse {
  collection_id: string;
  total: number;
  limit: number;
  offset: number;
  items: ConfigVersionSummary[];
}

export interface ConfigVersionDetail extends ConfigVersionSummary {
  config: Record<string, unknown>;
}

export interface ConfigDiffEntry {
  path: string;
  op: "added" | "removed" | "changed";
  before?: unknown;
  after?: unknown;
}

export interface ConfigVersionDiffResponse {
  collection_id: string;
  from_version: number;
  to_version: number;
  changes: ConfigDiffEntry[];
}

export interface ConfigVersionRestoreResponse {
  collection_id: string;
  restored_from: number;
  version: number;
  needs_reindex: boolean;
}

const base = (collectionId: string) => `${COLLECTIONS_BASE}/${collectionId}/config-versions`;

/** One newest-first page of the history. */
export function listConfigVersions(collectionId: string, limit = 50, offset = 0): Promise<ConfigVersionListResponse> {
  return apiFetch(`${base(collectionId)}?limit=${limit}&offset=${offset}`);
}

/** The structured, secret-masked diff from one version to another. */
export function diffConfigVersions(collectionId: string, from: number, to: number): Promise<ConfigVersionDiffResponse> {
  return apiFetch(`${base(collectionId)}/diff?from=${from}&to=${to}`);
}

/** Restore a version — always writes a NEW version ("restore of vN"). */
export function restoreConfigVersion(collectionId: string, version: number): Promise<ConfigVersionRestoreResponse> {
  return apiFetch(`${base(collectionId)}/${version}/restore`, { method: "POST" });
}
