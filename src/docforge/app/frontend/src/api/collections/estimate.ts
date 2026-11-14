// ====== Code Summary ======
// Cost estimation of a collection: the per-collection PARTIAL rate/assumption overrides and the
// read-only cost/volume dry-run estimate (never enqueues a job, never spends against a provider).

import { apiFetch, jsonInit } from "../http";
import type { DocumentFilter } from "../corpus";
import { COLLECTIONS_BASE as BASE } from "./base";

// ====== Cost-estimate overrides (per-collection PARTIAL overlay over the global rate/assumption defaults) ======
// Mirrors app/backend/libs/estimate/overrides.py — every field optional (an absent subtree falls
// through to the global default); stored verbatim in `Collection.estimate_overrides` and echoed on
// GET, written back via PATCH. No provider secrets are involved (prices only).

/** One chat/LLM/VLM model's (input, output) USD-per-1M-token price override. Both are required
 *  together — omit the model entry entirely (never a half-filled row) to fall back to the default. */
export interface ModelRateOverride {
  input: number;
  output: number;
}

/** Partial overrides of the three rate maps the estimator prices against (an absent map = default). */
export interface RateOverrides {
  /** Chat model id → (input, output) USD/1M-token override. */
  models?: Record<string, ModelRateOverride> | null;
  /** Embedding model id → USD/1M-token override. */
  embed?: Record<string, number> | null;
  /** OCR provider kind → USD/page override. */
  ocr?: Record<string, number> | null;
}

/**
 * Partial overrides of the estimator's extrapolation assumptions (mirrors `EstimateAssumptions`
 * field-for-field, every field optional). `target_chunk_tokens`/`chunk_overlap_ratio` are
 * DELIBERATELY not exposed here even though the backend model carries them: the collection's
 * actual chunker config always wins on top for those two (see EstimateOverrideMerger), so an
 * override would silently have zero effect — never surface a knob that does nothing.
 */
export interface AssumptionOverrides {
  tokens_per_page?: number | null;
  bytes_per_token?: number | null;
  bytes_per_page?: number | null;
  images_per_page?: number | null;
  scanned_page_ratio?: number | null;
  llm_prompt_overhead_tokens?: number | null;
  llm_output_tokens?: number | null;
  metagen_doc_context_tokens?: number | null;
  metagen_output_tokens_per_field?: number | null;
  vlm_prompt_tokens_per_image?: number | null;
  vlm_output_tokens?: number | null;
  embed_dense_dims?: number | null;
}

/** A collection's partial override of the cost-estimate inputs — rates and/or assumptions. */
export interface EstimateOverrides {
  rates?: RateOverrides | null;
  assumptions?: AssumptionOverrides | null;
}

// ====== Cost/volume dry-run estimate (read-only pipeline pricing preview) ======
// Mirrors POST /api/v1/collections/{id}/estimate — a read-only sweep across the collection's
// configured pipeline. Never enqueues a job and never spends against a provider.

/** "pending" (default) scopes the sweep to not-yet-ingested documents; "all" re-projects the whole collection. */
export type EstimateScope = "pending" | "all";

export interface EstimateRequest {
  scope?: EstimateScope;
  /** Estimate over exactly these document ids — mutually exclusive with `filter`; when either is
   *  set, `scope` is ignored server-side. */
  document_ids?: string[] | null;
  /** Estimate over the documents matching this corpus filter (the document-grid filter shape) —
   *  mutually exclusive with `document_ids`. */
  filter?: DocumentFilter | null;
}

/** An explicit subset selector for a targeted estimate — mirrors the backend's document_ids-XOR-filter
 *  contract exactly. Unlike the corpus bulk-op `DocumentSelector`, there is no `exclude_ids` escape
 *  hatch: a subset estimate is a preview, not a mutation, so a "select all minus a few" selection
 *  collapses to its plain filter. */
export type EstimateSubset = { document_ids: string[]; filter?: never } | { filter: DocumentFilter; document_ids?: never };

/**
 * One pipeline stage's projected usage and price. `cost_usd`/`rate_known` are `null`/`false` when
 * the stage's provider has no configured rate card — that is distinct from a genuinely free stage,
 * which reports `cost_usd: 0` with `rate_known: true`.
 */
export interface CostEstimateStage {
  stage: string;
  family: string;
  provider: string;
  model: string | null;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  pages: number;
  cost_usd: number | null;
  rate_known: boolean;
}

/** Projected ingest output volume — independent of pricing, always known even for an unpriced pipeline. */
export interface CostEstimateVolume {
  pages: number;
  chunks: number;
  dense_vectors: number;
  sparse_vectors: number;
  storage_bytes: number;
}

/**
 * Full dry-run estimate for a collection. `total_cost_usd` is `null` whenever at least one paid
 * stage's model has no known rate (`cost_complete` false) — never conflated with `0.0`, which
 * means an actually-free/parse-only pipeline. `total_cost_lower_bound_usd` is the sum of the priced
 * stages (the total when complete, else a minimum); a caveat names each unpriced model.
 */
export interface CostEstimate {
  document_count: number;
  stages: CostEstimateStage[];
  volume: CostEstimateVolume;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost_usd: number | null;
  total_cost_lower_bound_usd?: number;
  cost_complete: boolean;
  assumptions: Record<string, unknown>;
  caveats: string[];
}

/**
 * Runs the dry-run cost/volume estimate — read-only, no job enqueued, no provider spend.
 *
 * `subset`, when given, targets an explicit document id list or a corpus filter instead of the
 * whole-collection `scope` (which is then ignored server-side, mirroring the backend precedence).
 */
export function estimateCollectionCost(
  id: string,
  scope: EstimateScope = "pending",
  subset?: EstimateSubset,
): Promise<CostEstimate> {
  const request: EstimateRequest = subset ? { ...subset } : { scope };
  return apiFetch(`${BASE}/${id}/estimate`, jsonInit("POST", request));
}
