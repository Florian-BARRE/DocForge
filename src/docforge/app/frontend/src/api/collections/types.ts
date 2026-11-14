// ====== Code Summary ======
// TypeScript mirror of the collections REST contract: the Collection read model and its
// create/update request/response shapes. Shapes copied verbatim from the backend's Pydantic
// models (see /openapi.json) — nothing invented.

import type { EstimateOverrides } from "./estimate";
import type { FieldOp, FieldSpec, SchemaDiff } from "./schema";

export interface Collection {
  id: string;
  name: string;
  supported_formats: string[];
  /** Free-form labels for grouping/filtering collections in the UI (`[]` = untagged). */
  tags: string[];
  max_file_size_bytes: number;
  /** Whole-ingest-job wall-clock job timeout override, in seconds; `null` inherits the worker's global default. */
  job_timeout_seconds: number | null;
  needs_reindex: boolean;
  /**
   * Named vectors (`meta_<slug>_dense` / `meta_<slug>_bm25`) the schema's semantic/lexical fields need
   * but the vector store does not declare: those fields are unsearchable until the index is rebuilt.
   * Set on the single-collection read and the PATCH response; `null` on fleet-list rows.
   */
  missing_vectors?: string[] | null;
  /**
   * Aliases pointing at this collection (each usable in place of the UUID and as an `alias:<name>`
   * key scope). Set on the single-collection read only; `null`/absent on every other payload.
   */
  aliases?: string[] | null;
  created_at: string | null;
  /** `null` when the calling key lacks `read_technical` (the blob is withheld, not refused). */
  pipeline: Record<string, unknown> | null;
  /** `null` when the calling key lacks `read_technical` (the blob is withheld, not refused). */
  search: Record<string, unknown> | null;
  fields: FieldSpec[];
  /** Per-collection PARTIAL cost-estimate overrides (rates/assumptions); `null` = use the global defaults. */
  estimate_overrides: EstimateOverrides | null;
  /** Execution-trace capture level for this collection's ingest runs: `shape` (default) keeps only
   *  the cheap inline shape summary of each node's input/output; `full` also stores the raw payload
   *  in the object store (clamped by the operator ceiling `WORKER_TRACE_MAX_VERBOSITY`). Set via the
   *  wizard's first-class `TraceVerbosityField` (StepIdentity) — plumbed through the contract's
   *  `extraContract` overflow bag, same as every other schema-driven field with no named slot. */
  trace_verbosity: "shape" | "full";
  /** Document-scope field whose value is shown as each document's title; null = use the parsed title. */
  title_field: string | null;
}

/** Stock ingestion pipeline a new collection starts on when no explicit `pipeline` is posted. */
export type CollectionPreset = "standard" | "light";

export interface CreateCollectionRequest {
  name: string;
  supported_formats: string[];
  /** Free-form labels; `[]`/omitted creates the collection untagged. */
  tags?: string[] | null;
  max_file_size_bytes: number;
  /** `null`/omitted inherits the worker's global default job timeout. */
  job_timeout_seconds?: number | null;
  fields: FieldSpec[];
  /** Document-scope field used as the display title (must name a document-scope field). */
  title_field?: string | null;
  pipeline?: Record<string, unknown> | null;
  /** Stock-blob selector (ignored when `pipeline` is set): "light" = fast, enrichment-free core. */
  preset?: CollectionPreset | null;
}

/** PATCH result: the collection (unchanged under `dry_run`) plus its schema diff. */
export interface UpdateCollectionResponse extends Collection {
  dry_run: boolean;
  schema_diff: SchemaDiff;
}

/**
 * Patch payload — every field optional, mirroring the backend's diff semantics. The schema is sent
 * as EITHER `fields` (the FULL target schema: omitted fields are removed together with their stored
 * values, a changed name is remove + add) OR `field_ops` (explicit ops; `rename` keeps the values) —
 * both at once is a 422. `dry_run` validates and returns the `schema_diff` without writing anything.
 * A searchable-surface change flips `needs_reindex` on the returned Collection.
 */
export interface UpdateCollectionRequest {
  name?: string | null;
  supported_formats?: string[] | null;
  /** Replace the collection's labels wholesale (`[]` clears them); omitted = leave unchanged. */
  tags?: string[] | null;
  max_file_size_bytes?: number | null;
  /** `null` reverts to inheriting the worker's global default job timeout. */
  job_timeout_seconds?: number | null;
  fields?: FieldSpec[] | null;
  field_ops?: FieldOp[] | null;
  /** Preview only: nothing is written, the response carries the would-be `schema_diff`. */
  dry_run?: boolean;
  /** Display-title field; explicit `null` clears it. Backend answers 422 listing valid choices on a bad name. */
  title_field?: string | null;
  pipeline?: Record<string, unknown> | null;
  search?: Record<string, unknown> | null;
  /** Partial cost-estimate overrides. Omitted = leave unchanged; explicit `null` clears back to the
   *  global defaults; a value replaces the stored overrides wholesale. */
  estimate_overrides?: EstimateOverrides | null;
  note?: string | null;
}
