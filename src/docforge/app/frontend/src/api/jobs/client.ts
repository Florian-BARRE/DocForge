// ====== Code Summary ======
// Typed client of the jobs REST resource: paginated listing, single job, cancel, trace/event
// payloads, and the monitoring aggregates (durations, cost, workers, queue, failures, timeseries).

import { apiFetch } from "../http";
import { JOBS_BASE as BASE } from "./base";
import type {
  CollectionCost, JobEventPayload, JobEventPayloadSlot, JobListParams, JobPage, JobStatus, JobStatusValue, JobTrace,
  QueueDepth, StageDurations, WorkersLive,
} from "./types";

/**
 * List one bounded page of jobs — a collection's, or (with no `collectionId`) the whole fleet's.
 *
 * Returns the BOUNDED, paginated envelope (`{total, limit, offset, jobs}`) verbatim so a caller can
 * drive a pager. `status`/`stage`/`errorType`/`search`/`createdAfter`/`createdBefore` are additive
 * triage facets; `sort` picks the dimension (created/duration/status) and `order` its direction
 * (newest-first default). The page size is server-clamped to `JOBS_MAX_PAGE_SIZE`.
 */
export async function listJobsPage(params: JobListParams = {}): Promise<JobPage> {
  const query = new URLSearchParams();
  if (params.collectionId) query.set("collection_id", params.collectionId);
  if (params.stage) query.set("stage", params.stage);
  if (params.errorType) query.set("error_type", params.errorType);
  if (params.search) query.set("search", params.search);
  if (params.createdAfter) query.set("created_after", params.createdAfter);
  if (params.createdBefore) query.set("created_before", params.createdBefore);
  if (params.sort) query.set("sort", params.sort);
  if (params.order) query.set("order", params.order);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  // Repeat `status` once per value — the backend reads it as a repeated query param.
  for (const status of params.status ?? []) query.append("status", status);
  const qs = query.toString();
  return apiFetch<JobPage>(`${BASE}${qs ? `?${qs}` : ""}`);
}

/**
 * List a collection's jobs, newest first — the convenience unwrap for the per-collection views.
 *
 * Returns just the first page's rows (server-clamped to `JOBS_MAX_PAGE_SIZE`); callers that need the
 * pager envelope, fleet-wide scope, a status filter or FIFO order use `listJobsPage` instead.
 */
export async function listJobs(collectionId: string): Promise<JobStatus[]> {
  const page = await listJobsPage({ collectionId });
  return page.jobs;
}

export function getJob(jobId: string): Promise<JobStatus> {
  return apiFetch(`${BASE}/${jobId}`);
}

/** The coarse outcome of a cancel call: the job is now terminal, or a running job was only
 *  flagged to stop cooperatively at its next stage boundary (still `status: "running"`). */
export type CancelOutcome = "cancelled" | "cancellation_requested";

export interface CancelResult {
  job_id: string;
  status: JobStatusValue;
  cancel_requested: boolean;
  outcome: CancelOutcome;
  detail: string;
}

/**
 * Stop an ingestion job — cooperatively for a running job, immediately for a queued or wedged one.
 *
 * `force=false` (default) on a queued job cancels it now; on a running job it requests a
 * cooperative stop at the next stage boundary. `force=true` force-terminates a running job
 * immediately regardless of worker state — the manual escape hatch for a wedged/looping job.
 * Throws `HttpError` 409 when the job is already terminal (done/failed/cancelled).
 */
export function cancelJob(jobId: string, force: boolean): Promise<CancelResult> {
  return apiFetch(`${BASE}/${jobId}/cancel?force=${force}`, { method: "POST" });
}

export function getJobTrace(jobId: string): Promise<JobTrace> {
  return apiFetch(`${BASE}/${jobId}/events`);
}

/**
 * Fetch one trace node's FULL raw payload for a single slot — the lazy deep-dive behind a node's
 * "Load input"/"Load output" button (never fetched automatically; a full IR can be heavy).
 *
 * Throws `HttpError` 404 when the addressed event only carries a shape summary (no full payload was
 * captured for that slot, or it aged out) — callers should render a dim "no full payload" state.
 */
export function getEventPayload(
  jobId: string,
  eventId: string,
  slot: JobEventPayloadSlot,
): Promise<JobEventPayload> {
  return apiFetch(`${BASE}/${jobId}/events/${eventId}/payload?slot=${slot}`);
}

export function getStageDurations(collectionId: string): Promise<StageDurations> {
  return apiFetch(`${BASE}/stage-durations?collection_id=${encodeURIComponent(collectionId)}`);
}

export function getCollectionCost(collectionId: string): Promise<CollectionCost> {
  return apiFetch(`${BASE}/cost?collection_id=${encodeURIComponent(collectionId)}`);
}

export function getWorkersLive(): Promise<WorkersLive> {
  return apiFetch(`${BASE}/workers/live`);
}

/**
 * Return the backlog depth — pending (queued, unclaimed) and running job counts.
 *
 * Fleet-wide when `collectionId` is omitted, otherwise scoped to that collection.
 */
export function getQueueDepth(collectionId?: string): Promise<QueueDepth> {
  const query = collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : "";
  return apiFetch(`${BASE}/queue${query}`);
}

/** One failure-breakdown bucket — a cause/stage label and how many failed jobs carry it. `"unknown"`
 *  is a real value (the literal the backend emits for a null group key), not an absence marker. */
export interface FailureBucket {
  label: string;
  count: number;
}

/** One failure-breakdown bucket grouped by collection. */
export interface CollectionFailureBucket {
  collection_id: string;
  collection_name: string | null;
  count: number;
}

/** Failure aggregation over a time window — the "why is it breaking" panel's data. */
export interface FailureBreakdown {
  collection_id: string | null;
  window_hours: number;
  since: string;
  total_failed: number;
  by_error_type: FailureBucket[];
  by_stage: FailureBucket[];
  by_collection: CollectionFailureBucket[];
}

export interface FailureBreakdownParams {
  collectionId?: string;
  /** Look-back window in hours (default 24, max 720/30d). */
  windowHours?: number;
}

/** Aggregate recent failures into top causes, by stage and by collection — the "why it breaks" panel. */
export function getFailureBreakdown(params: FailureBreakdownParams = {}): Promise<FailureBreakdown> {
  const query = new URLSearchParams();
  if (params.collectionId) query.set("collection_id", params.collectionId);
  if (params.windowHours !== undefined) query.set("window_hours", String(params.windowHours));
  const qs = query.toString();
  return apiFetch<FailureBreakdown>(`${BASE}/failures/breakdown${qs ? `?${qs}` : ""}`);
}

/** The "X new failures since you last looked" signal's response. */
export interface NewFailures {
  since: string;
  count: number;
  /** Ids of the new failures, newest first (bounded); populated only when `includeIds` was passed. */
  job_ids: string[];
  /** The newest failure's finish time — pass this back as the next `since` cursor. Null when `count` is 0. */
  latest_failed_at: string | null;
}

export interface NewFailuresParams {
  /** The client's last-seen cursor (ISO-8601) — only jobs that FAILED strictly after this count. */
  since: string;
  collectionId?: string;
  includeIds?: boolean;
  limit?: number;
}

/** Report how many jobs have failed since a cursor — the "X new failures since you last looked" badge. */
export function getNewFailures(params: NewFailuresParams): Promise<NewFailures> {
  const query = new URLSearchParams();
  query.set("since", params.since);
  if (params.collectionId) query.set("collection_id", params.collectionId);
  if (params.includeIds !== undefined) query.set("include_ids", String(params.includeIds));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  return apiFetch<NewFailures>(`${BASE}/failures/new?${query.toString()}`);
}

/** One hourly bucket of the job trends — arrivals, completions and reconstructed backlog. */
export interface TimeseriesBucket {
  bucket_start: string;
  created: number;
  done: number;
  failed: number;
  backlog: number;
}

/** Lightweight job trends — contiguous hourly buckets computed from the job table (no Prometheus). */
export interface JobTimeseries {
  collection_id: string | null;
  window_hours: number;
  bucket_seconds: number;
  buckets: TimeseriesBucket[];
}

export interface JobTimeseriesParams {
  collectionId?: string;
  /** Hours of history as hourly buckets (default 24, max 168/7d — the server cap). */
  windowHours?: number;
}

/** Return lightweight hourly job trends — done/h, failed/h, arrivals and backlog — for in-product sparklines. */
export function getJobTimeseries(params: JobTimeseriesParams = {}): Promise<JobTimeseries> {
  const query = new URLSearchParams();
  if (params.collectionId) query.set("collection_id", params.collectionId);
  if (params.windowHours !== undefined) query.set("window_hours", String(params.windowHours));
  const qs = query.toString();
  return apiFetch<JobTimeseries>(`${BASE}/timeseries${qs ? `?${qs}` : ""}`);
}
