// ====== Code Summary ======
// TypeScript mirror of the jobs (ingestion monitoring) REST contract + its typed client.

import { apiFetch, clearApiToken, getApiToken, HttpError } from "./http";

const BASE = "/api/v1/jobs";

// Mirrors the backend's JobStatus StrEnum verbatim (`pending`, not `queued`) — the `| string`
// fallback keeps this open to a future status without breaking the build. `cancelled` is the
// terminal state for a stopped job (queued-before-it-ran, cooperative stop honoured, or forced).
export type JobStatusValue = "pending" | "running" | "done" | "failed" | "cancelled" | string;

export interface JobStatus {
  job_id: string;
  document_id: string;
  /** The document's filename, joined at read — null only if the document row is gone. */
  document_filename: string | null;
  /** The document's metagen-generated title, joined at read — a nicer display label than the
   *  filename when present. Null if none was generated, the document is gone, or (SSE status
   *  frames only) the snapshot didn't re-join it — see streamJobEvents. */
  document_title: string | null;
  collection_id: string;
  /** The collection's name, joined at read — null only if the collection row is gone. */
  collection_name: string | null;
  status: JobStatusValue;
  /** A cooperative stop has been requested; a RUNNING job stops at its next stage boundary and
   *  stays `status: "running"` (with this flag set) until it does. */
  cancel_requested: boolean;
  progress: number;
  current_stage: string | null;
  error: string | null;
  attempt: number;
  started_at: string | null;
  finished_at: string | null;
  /** Last progress/lifecycle write — freezes when a job wedges. */
  updated_at: string;
  /** A RUNNING job idle past the stall threshold — an early wedge warning before the reaper fails it. */
  stalled: boolean;
  /** Wall-clock run time in seconds: finished_at − started_at for a terminal job, or now − started_at
   *  for a still-running one. Null while the job is queued (never started) — the sortable "duration"
   *  column of the triage view. */
  duration_seconds: number | null;
  /** Running total of prompt tokens billed across this job's paid text-gen calls. */
  total_prompt_tokens: number;
  /** Running total of completion tokens billed across this job's paid text-gen calls. */
  total_completion_tokens: number;
  /** Running USD cost of this job's paid calls (0 when nothing priceable ran). */
  cost_usd: number;
  /** Child items finished in the CURRENT fan-out stage; null when not in a fan-out stage. */
  items_done: number | null;
  /** The current fan-out stage's width; null when not in a fan-out stage. */
  items_total: number | null;
  /** Deepest node that raised — only set on a failed job. */
  failed_node_id: string | null;
  /** That node's kind/family label — only set on a failed job. */
  failed_node_kind: string | null;
  /** The fan-out item index the failure sits in; null outside a fan-out. */
  failed_item_index: number | null;
  /** Exception class name of the failure (e.g. "TimeoutError"); only set on a failed job. */
  error_type: string | null;
}

/** The one human label to show for a job, everywhere it's shown (job rows, worker cards, the job
 *  detail header): the metagen title when one was generated, else the filename, else a generic
 *  fallback for the rare gone-document edge case. Keeping this in one place is what keeps the job
 *  list and the job detail header in sync. */
export function jobDisplayName(job: Pick<JobStatus, "document_title" | "document_filename">): string {
  return job.document_title || job.document_filename || "untitled document";
}

export interface JobEvent {
  stage: string;
  status: string;
  /** The stage's structural kind (action/group/foreach) or the node's concrete kind — null for
   * rows written before this column landed. */
  node_kind: string | null;
  started_at: string | null;
  finished_at: string | null;
  detail: string | null;
  /** Prompt tokens billed by this stage's paid calls; null when the stage made none. */
  prompt_tokens: number | null;
  /** Completion tokens billed by this stage; null when none. */
  completion_tokens: number | null;
  /** USD cost of this stage; null when no usage or the model has no known price. */
  cost_usd: number | null;
  /** Quality score in [0, 1] of a scored-family node (parser/ocr/…) — what a ScoreBelow edge
   *  compares to its threshold. Null for non-scored nodes and legacy rows. */
  score: number | null;
  /** Materialized tree path — root = bare node id (e.g. "parse"), nested = dotted path (e.g.
   *  "enrich.figures.figbody[0].vlm"). Null for legacy rows (pre-tree). */
  node_path: string | null;
  /** Depth in the execution tree: 0 = root stage, larger = more nested. Null for legacy rows —
   *  the UI treats that as depth 0. */
  depth: number | null;
  /** node_path of this node's parent; null for root stages and legacy rows. */
  parent_path: string | null;
  /** Zero-based ForEach item index when this node runs inside a fan-out; null outside any
   *  fan-out (and for legacy rows). */
  item_index: number | null;
  /** The stage-event row's UUID — the stable handle `getEventPayload` addresses. */
  event_id: string;
  /** Bounded SHAPE descriptor of the node's resolved input (e.g. `{type, fields, sizes, hash}`) —
   *  NEVER the raw content. Null when trace capture was off, the node had no input, or legacy rows. */
  input_summary: Record<string, unknown> | null;
  /** Bounded SHAPE descriptor of the node's output — never the raw content. Null when trace
   *  capture was off, the node produced nothing, or for legacy rows. */
  output_summary: Record<string, unknown> | null;
  /** Whether a FULL raw input payload was stored (the opt-in full-capture tier) and can be fetched
   *  via `getEventPayload`. Null/false both mean unavailable. */
  has_full_input: boolean | null;
  /** Whether a FULL raw output payload was stored and can be fetched via `getEventPayload`. */
  has_full_output: boolean | null;
}

/** Which side of a traced node's payload to fetch. */
export type JobEventPayloadSlot = "input" | "output";

/** One trace node's FULL raw input or output payload, fetched on demand (never inlined in the trace
 *  list) — the on-demand deep-dive behind a node's "Load input"/"Load output" button. */
export interface JobEventPayload {
  job_id: string;
  event_id: string;
  slot: JobEventPayloadSlot;
  stage: string;
  node_path: string | null;
  /** True when the stored object exceeded the server's read cap — `payload` is then null and only
   *  `size_bytes` describes it. */
  truncated: boolean;
  size_bytes: number;
  /** The node's full raw payload (arbitrary JSON), or null when `truncated`. */
  payload: unknown;
}

/** Per-stage average wall-clock (seconds) across the collection's completed jobs — the ETA basis. */
export interface StageDurations {
  collection_id: string;
  stage_seconds: Record<string, number>;
}

/** A collection's rolled-up ingestion spend across all its jobs. */
export interface CollectionCost {
  collection_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  cost_usd: number;
  document_count: number;
}

export interface JobTrace {
  job_id: string;
  events: JobEvent[];
}

export interface WorkerActivity {
  worker_id: string;
  /** Friendly display name (WORKER_NAME, defaults to the hostname); null for a pre-column heartbeat row. */
  worker_name: string | null;
  /** Heartbeat fresher than the liveness threshold (~30s) — independent of `busy`. */
  alive: boolean;
  /** Owns at least one RUNNING job right now — independent of `alive`. */
  busy: boolean;
  /** Last heartbeat tick; null when the worker has no heartbeat row yet. */
  last_seen: string | null;
  /** When the worker process registered; null when no heartbeat row exists. */
  started_at: string | null;
  /**
   * The worker's configured parallel-job capacity (arq concurrency, = WORKER_CONCURRENCY); null =
   * unknown capacity (an old heartbeat row, or a worker on a build predating this field).
   */
  max_jobs: number | null;
  /**
   * Recent CPU utilisation percent, sampled (via psutil) at the last heartbeat tick — may exceed
   * 100 on a multi-core host; null = not reported (old row, non-sampling build, first unprimed tick,
   * or a psutil error).
   */
  cpu_percent: number | null;
  /** Resident memory (RSS) in megabytes at the last heartbeat tick; null = not reported. */
  mem_mb: number | null;
  /** Resident memory as a percent of total host RAM at the last heartbeat tick; null = not reported. */
  mem_percent: number | null;
  jobs: JobStatus[];
}

export interface WorkersLive {
  workers: WorkerActivity[];
}

/** Backlog counters — pending (queued, unclaimed) and running job counts. */
export interface QueueDepth {
  pending: number;
  running: number;
}

/** One paginated page of a collection's jobs — mirrors the backend's bounded-list envelope. */
export interface JobPage {
  total: number;
  limit: number;
  offset: number;
  jobs: JobStatus[];
}

/** Sort order for the jobs list: `newest` = created_at DESC (default), `oldest` = created_at ASC
 *  (FIFO — the "what runs next" order, typically paired with `status: ["pending"]`). Also the
 *  DIRECTION applied to `sort` (duration: longest/shortest-first; status: z-a/a-z). */
export type JobOrder = "newest" | "oldest";

/** Sort dimension for the jobs list triage view — `created` (default), `duration` (wall-clock run
 *  time — a queued job sorts last), or `status`. */
export type JobSort = "created" | "duration" | "status";

/** Query filters for `GET /jobs`. Omit `collectionId` for a FLEET-WIDE listing (full-access keys
 *  only) — the "All Jobs" management view. `status` is repeatable (any subset of the job statuses). */
export interface JobListParams {
  collectionId?: string;
  status?: JobStatusValue[];
  /** Filter to jobs in this stage (the node's current_stage) — the triage "stage" facet. */
  stage?: string;
  /** Filter to jobs with this structured failure class (e.g. "TimeoutError") — the "error class" facet. */
  errorType?: string;
  /** Case-insensitive PREFIX match on the job id OR the document id. */
  search?: string;
  /** Keep only jobs created at or after this instant (ISO-8601) — the date-range start. */
  createdAfter?: string;
  /** Keep only jobs created at or before this instant (ISO-8601) — the date-range end. */
  createdBefore?: string;
  sort?: JobSort;
  order?: JobOrder;
  limit?: number;
  offset?: number;
}

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

/** Callbacks the live job stream drives — one per new stage event, one per status snapshot change. */
export interface JobStreamHandlers {
  onEvent: (event: JobEvent) => void;
  onStatus: (status: JobStatus) => void;
  signal?: AbortSignal;
}

/**
 * Consume a job's live SSE feed (`GET /jobs/{id}/stream`) until it closes at terminal state.
 *
 * The API is header-only auth (Authorization: Bearer), which the native EventSource cannot set — so
 * we open the stream with `fetch` (which CAN carry the header) and parse the `data: {json}\n\n`
 * frames off the ReadableStream ourselves. Each frame carries a `kind` — `"event"` (a stage event)
 * or `"status"` (a JobStatus snapshot). Resolves when the server closes the stream (job terminal),
 * rejects on a non-2xx open or a transport error so callers can fall back to polling.
 */
export async function streamJobEvents(jobId: string, handlers: JobStreamHandlers): Promise<void> {
  const token = getApiToken();
  const response = await fetch(`${BASE}/${jobId}/stream`, {
    headers: {
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: handlers.signal,
  });
  if (!response.ok || !response.body) {
    if (response.status === 401) clearApiToken();
    throw new HttpError(response.status, [{ message: `Stream failed (${response.status})` }]);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line. Drain every complete frame in the buffer.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawFrame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = rawFrame.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const payload = dataLine.slice(dataLine.indexOf(":") + 1).trim();
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(payload);
      } catch {
        continue; // partial/garbled frame — skip it, never crash the stream
      }
      if (frame.kind === "event") handlers.onEvent(frame as unknown as JobEvent);
      else if (frame.kind === "status") handlers.onStatus(frame as unknown as JobStatus);
    }
  }
}
