// ====== Code Summary ======
// TypeScript mirror of the collections REST contract + its typed client. Shapes copied verbatim
// from the backend's Pydantic models (see /openapi.json) — nothing invented.

import { apiFetch, jsonInit } from "./http";

const BASE = "/api/v1/collections";

export type FieldType = "string" | "integer" | "float" | "bool" | "keyword_list" | "datetime" | "enum" | "text" | "integer_list" | "float_list" | "text_list";
export type FieldOrigin = "system" | "user" | "generated";
export type FieldScope = "document" | "chunk";

/** Canonical value lists (mirrors the backend StrEnums) — every select renders from these, never from an inline literal. */
export const FIELD_TYPES: FieldType[] = ["string", "integer", "float", "bool", "keyword_list", "datetime", "enum", "text", "integer_list", "float_list", "text_list"];
export const FIELD_ORIGINS: FieldOrigin[] = ["system", "user", "generated"];
export const FIELD_SCOPES: FieldScope[] = ["document", "chunk"];

export interface FieldSpec {
  field_name: string;
  field_type: FieldType;
  required: boolean;
  filterable: boolean;
  lexical: boolean;
  semantic: boolean;
  enum_values: string[] | null;
  origin: FieldOrigin;
  scope: FieldScope;
}

export interface Collection {
  id: string;
  name: string;
  supported_formats: string[];
  max_file_size_bytes: number;
  needs_reindex: boolean;
  created_at: string | null;
  pipeline: Record<string, unknown>;
  search: Record<string, unknown>;
  fields: FieldSpec[];
}

export interface CreateCollectionRequest {
  name: string;
  supported_formats: string[];
  max_file_size_bytes: number;
  fields: FieldSpec[];
  pipeline?: Record<string, unknown> | null;
}

/**
 * Patch payload — every field optional, mirroring the backend's diff semantics: `fields` is the
 * FULL target schema (fields omitted from the list are removed, together with their stored
 * values); a searchable-surface change flips `needs_reindex` on the returned Collection.
 */
export interface UpdateCollectionRequest {
  name?: string | null;
  supported_formats?: string[] | null;
  max_file_size_bytes?: number | null;
  fields?: FieldSpec[] | null;
  pipeline?: Record<string, unknown> | null;
  search?: Record<string, unknown> | null;
  note?: string | null;
}

export function listCollections(): Promise<Collection[]> {
  return apiFetch(BASE);
}

export function getCollection(id: string): Promise<Collection> {
  return apiFetch(`${BASE}/${id}`);
}

export function createCollection(request: CreateCollectionRequest): Promise<Collection> {
  return apiFetch(BASE, jsonInit("POST", request));
}

export function updateCollection(id: string, request: UpdateCollectionRequest): Promise<Collection> {
  return apiFetch(`${BASE}/${id}`, jsonInit("PATCH", request));
}

export function deleteCollection(id: string): Promise<void> {
  return apiFetch(`${BASE}/${id}`, { method: "DELETE" });
}
