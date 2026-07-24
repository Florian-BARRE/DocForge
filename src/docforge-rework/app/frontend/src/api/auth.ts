// ====== Code Summary ======
// TypeScript mirror of the API-key auth REST contract + its typed client. Shapes copied verbatim
// from the backend's Pydantic models — nothing invented.

import { apiFetch, jsonInit } from "./http";

const BASE = "/api/v1/auth/keys";

export type ApiCapability = "read" | "write" | "search" | "admin";

/** Canonical value list — the capability checkboxes render from this, never an inline literal. */
export const API_CAPABILITIES: ApiCapability[] = ["read", "write", "search", "admin"];

/** `collections: ["*"]` means every collection; otherwise an explicit list of collection UUIDs. */
export interface KeyPermissions {
  capabilities: ApiCapability[];
  collections: string[];
}

export const ALL_COLLECTIONS_SCOPE = "*";

/** A stored key as returned by list/create — never carries the plaintext or its hash. */
export interface ApiKeyInfo {
  id: string;
  name: string;
  prefix: string;
  /** `null` means full access (no restriction). */
  permissions: KeyPermissions | null;
  created_at: string;
  revoked_at: string | null;
}

/** Same shape as `ApiKeyInfo`, plus the plaintext key — shown ONCE, on creation only. */
export interface CreatedApiKey extends ApiKeyInfo {
  key: string;
}

export interface CreateApiKeyRequest {
  name: string;
  permissions?: KeyPermissions | null;
}

export function createKey(request: CreateApiKeyRequest): Promise<CreatedApiKey> {
  return apiFetch(BASE, jsonInit("POST", request));
}

export function listKeys(): Promise<ApiKeyInfo[]> {
  return apiFetch(BASE);
}

export function revokeKey(id: string): Promise<void> {
  return apiFetch(`${BASE}/${id}`, { method: "DELETE" });
}
