// ====== Code Summary ======
// TypeScript mirror of the API-key auth REST contract + its typed client. Shapes copied verbatim
// from the backend's Pydantic models — nothing invented.

import { apiFetch, jsonInit } from "./http";

const BASE = "/api/v1/auth/keys";

/**
 * `read` is the legacy pre-split alias (= `read_text` + `read_technical`): a key stored before the
 * split may still carry it, but it is never offered for a new key.
 */
export type ApiCapability = "read" | "read_text" | "read_technical" | "write" | "search" | "create" | "admin";

/** Canonical value list — the capability checkboxes render from this, never an inline literal. */
export const API_CAPABILITIES: ApiCapability[] = ["read_text", "read_technical", "write", "search", "create", "admin"];

/** Named capability presets — the server expands one into its explicit capability list. */
export type KeyProfile = "agent_reader" | "agent_searcher" | "operator" | "admin";

/** Each profile with its one-line intent, in offer order (the server owns the capability lists). */
export const KEY_PROFILES: { value: KeyProfile; hint: string }[] = [
  { value: "agent_reader", hint: "business chatbot — reads documents as text + searches, no internals" },
  { value: "agent_searcher", hint: "search only" },
  { value: "operator", hint: "text + technical reads (IR, traces, exports, ops) + write" },
  { value: "admin", hint: "every capability, within the collection scope" },
];

/** A stored grant — `collections: ["*"]` means every collection, else explicit collection UUIDs. */
export interface KeyPermissions {
  capabilities: ApiCapability[];
  collections: string[];
  /** The preset the key was created from (display only; `capabilities` is authoritative). */
  profile?: KeyProfile | null;
}

/** A grant as SENT — either an explicit `capabilities` list or a `profile` the server expands. */
export interface KeyPermissionsRequest {
  capabilities?: ApiCapability[];
  collections: string[];
  profile?: KeyProfile | null;
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
  /** `null` means the key never expires. */
  expires_at: string | null;
  /** `null` means the key has never been used. */
  last_used_at: string | null;
}

/** Same shape as `ApiKeyInfo`, plus the plaintext key — shown ONCE, on creation/rotation only. */
export interface CreatedApiKey extends ApiKeyInfo {
  key: string;
}

export interface CreateApiKeyRequest {
  name: string;
  permissions?: KeyPermissionsRequest | null;
  expires_at?: string | null;
}

/** Every field overrides; the backend clones the old value only for fields left out. */
export interface RotateApiKeyRequest {
  name?: string;
  permissions?: KeyPermissionsRequest | null;
  expires_at?: string | null;
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

/** Issues a new secret for `id`, applying the given fields, and revokes the old key. */
export function rotateKey(id: string, request: RotateApiKeyRequest): Promise<CreatedApiKey> {
  return apiFetch(`${BASE}/${id}/rotate`, jsonInit("POST", request));
}
