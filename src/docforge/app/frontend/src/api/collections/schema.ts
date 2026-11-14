// ====== Code Summary ======
// Collection schema contract: the field spec/enum mirrors, explicit field ops, the schema diff a
// PATCH reports, and the JSON-Schema discovery call of the collection identity/limits contract.
// Shapes copied verbatim from the backend's Pydantic models (see /openapi.json) — nothing invented.

import { apiFetch } from "../http";
import type { JsonSchema } from "../types";
import { COLLECTIONS_BASE as BASE } from "./base";

// mirror of backend StrEnums (app/backend/routers/collections/models.py) — keep in sync; no
// discovery/enums endpoint currently exposes these, so they stay hand-copied until one does.
export type FieldType = "string" | "integer" | "float" | "bool" | "keyword_list" | "datetime" | "enum" | "text" | "integer_list" | "float_list" | "text_list";
export type FieldOrigin = "system" | "user" | "generated";
export type FieldScope = "document" | "chunk";

/** Canonical value lists (mirrors the backend StrEnums) — every select renders from these, never from an inline literal. */
export const FIELD_TYPES: FieldType[] = ["string", "integer", "float", "bool", "keyword_list", "datetime", "enum", "text", "integer_list", "float_list", "text_list"];
export const FIELD_ORIGINS: FieldOrigin[] = ["system", "user", "generated"];
export const FIELD_SCOPES: FieldScope[] = ["document", "chunk"];

/** Mirror of the backend's FieldSpecModel.description max_length. */
export const FIELD_DESCRIPTION_MAX_LENGTH = 1000;

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
  /** What the field means — shown to search agents and in describe_collection; null when unset. */
  description: string | null;
}

/** Partial attribute change of an existing field (mirrors the backend `FieldPatch`); values are kept. */
export type FieldPatch = Partial<Omit<FieldSpec, "field_name">>;

/** Explicit schema operations (mirror of the backend field-op union) — applied in order by the PATCH. */
export type FieldOp =
  | { op: "add"; field: FieldSpec }
  | { op: "update"; field_name: string; changes: FieldPatch }
  | { op: "remove"; field_name: string }
  | { op: "rename"; field_name: string; new_name: string };

export interface SchemaDiffModifiedField {
  field_name: string;
  changed_attrs: string[];
}

export interface SchemaDiffRename {
  from_name: string;
  to_name: string;
}

/** The schema change a PATCH applied (or, under `dry_run`, would apply). */
export interface SchemaDiff {
  added?: string[];
  modified?: SchemaDiffModifiedField[];
  /** Deleted fields — their stored values go with them (see `values_lost`). */
  removed?: string[];
  renamed?: SchemaDiffRename[];
  /** Removed field -> number of stored document + chunk values deleted with it. */
  values_lost?: Record<string, number>;
  /** Fields needing a reindex before they are searchable. */
  reindex_required_fields?: string[];
}


/** Mirrors a node card's `config_schema` face — see `GET /collections/contract-schema`. */
interface CollectionContractSchemaResponse {
  config_schema: JsonSchema;
}

/**
 * Discover the collection identity/limits contract as JSON Schema — fed straight into the
 * shared `SchemaForm`, exactly like a node's `config_schema`, so a new backend contract field
 * auto-surfaces in the wizard with zero further frontend edit.
 */
export async function fetchCollectionContractSchema(): Promise<JsonSchema> {
  const response = await apiFetch<CollectionContractSchemaResponse>(`${BASE}/contract-schema`);
  return response.config_schema;
}
