// ====== Code Summary ======
// Shared contract helpers for the stage-replay reingest: the replayable stage keys, plus typed
// readers for the three structured refusals the reingest routes can answer (422 replay_unsupported,
// 409 estimate_required, 429 queue_saturated). Each reader inspects an HttpError and returns null
// when the error is not that refusal, so callers branch without re-parsing the detail.

import { HttpError } from "./http";

/** Post-IR stages a reingest can replay from (`contextualize` never is — replay from `chunk`). */
export const REPLAY_STAGES = ["enrich", "chunk", "metagen_chunk", "metagen_document", "embed"] as const;

/** `null` = full re-ingest; otherwise a stage key to replay from on the persisted IR. */
export type ReplayFrom = string | null;

export interface ReplayUnsupported {
  reason: string;
  allowed: string[];
}

export interface ReingestEstimate {
  document_count: number;
  total_cost_usd: number;
  total_cost_lower_bound_usd: number;
  cost_complete: boolean;
  priced_stages: string[];
  caveats: string[];
}

export interface EstimateRequired {
  message: string;
  matched: number;
  threshold: number;
  /** Null when the server-side estimator failed. */
  estimate: ReingestEstimate | null;
}

export interface QueueSaturated {
  retryAfterSeconds: number | null;
}

function detailWithCode(error: unknown, status: number, code: string): Record<string, unknown> | null {
  if (!(error instanceof HttpError) || error.status !== status) return null;
  return error.detail?.code === code ? error.detail : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

export function readReplayUnsupported(error: unknown): ReplayUnsupported | null {
  const detail = detailWithCode(error, 422, "replay_unsupported");
  if (!detail) return null;
  return { reason: typeof detail.reason === "string" ? detail.reason : "This stage cannot be replayed.", allowed: strings(detail.allowed) };
}

export function readEstimateRequired(error: unknown): EstimateRequired | null {
  const detail = detailWithCode(error, 409, "estimate_required");
  if (!detail) return null;
  const raw = detail.estimate as Record<string, unknown> | null | undefined;
  const estimate: ReingestEstimate | null = raw
    ? {
        document_count: Number(raw.document_count ?? 0),
        total_cost_usd: Number(raw.total_cost_usd ?? 0),
        total_cost_lower_bound_usd: Number(raw.total_cost_lower_bound_usd ?? 0),
        cost_complete: raw.cost_complete === true,
        priced_stages: strings(raw.priced_stages),
        caveats: strings(raw.caveats),
      }
    : null;
  return {
    message: typeof detail.message === "string" ? detail.message : "This reingest is large — review the estimate first.",
    matched: Number(detail.matched ?? 0),
    threshold: Number(detail.threshold ?? 0),
    estimate,
  };
}

export function readQueueSaturated(error: unknown): QueueSaturated | null {
  if (!(error instanceof HttpError) || error.status !== 429) return null;
  if (error.detail && error.detail.code !== "queue_saturated") return null;
  return { retryAfterSeconds: error.retryAfterSeconds };
}
