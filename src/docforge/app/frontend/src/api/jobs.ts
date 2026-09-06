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
 *  (FIFO — the "what runs next" order, typically paired with `status: ["pending"]`). */
export type JobOrder = "newest" | "oldest";

/** Query filters for `GET /jobs`. Omit `collectionId` for a FLEET-WIDE listing (full-access keys
 *  only) — the "All Jobs" management view. `status` is repeatable (any subset of the job statuses). */
export interface JobListParams {
  collectionId?: string;
  status?: JobStatusValue[];
  order?: JobOrder;
  limit?: number;
  offset?: number;
}

/**
 * List one bounded page of jobs — a collection's, or (with no `collectionId`) the whole fleet's.
 *
 * Returns the BOUNDED, paginated envelope (`{total, limit, offset, jobs}`) verbatim so a caller can
 * drive a pager. `status` filters by one or more job statuses; `order` picks newest-first (default)
 * or oldest-first/FIFO. The page size is server-clamped to `JOBS_MAX_PAGE_SIZE`.
 */
export async function listJobsPage(params: JobListParams = {}): Promise<JobPage> {
  const query = new URLSearchParams();
  if (params.collectionId) query.set("collection_id", params.collectionId);
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
