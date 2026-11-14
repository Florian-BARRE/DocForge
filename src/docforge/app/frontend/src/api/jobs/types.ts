// ====== Code Summary ======
// TypeScript mirror of the jobs (ingestion monitoring) REST contract: status/kind enums and their
// display helpers, job/event/trace/worker read models and the list-query parameters.

// Mirrors the backend's JobStatus StrEnum verbatim (`pending`, not `queued`) — the `| string`
// fallback keeps this open to a future status without breaking the build. `cancelled` is the
// terminal state for a stopped job (queued-before-it-ran, cooperative stop honoured, or forced).
export type JobStatusValue = "pending" | "running" | "done" | "failed" | "cancelled" | string;

/** What a job tracks: a full pipeline run or a lightweight per-document metadata re-embed. Open
 *  `| string` like JobStatusValue so a future backend kind degrades to its raw label. */
export type JobKindValue = "ingest" | "metadata_sync" | "rebuild_index" | string;

const JOB_KIND_LABEL: Record<string, string> = {
  ingest: "ingestion",
  metadata_sync: "metadata sync",
  rebuild_index: "index rebuild",
};

/** Human label for a job kind; unknown kinds fall back to the raw enum with underscores softened. */
export function jobKindLabel(kind: JobKindValue): string {
  return JOB_KIND_LABEL[kind] ?? kind.replace(/_/g, " ");
}

/** Only ingest jobs carry cache/force re-run semantics (a missing kind = a pre-kind payload = ingest). */
export function isIngestJob(job: Pick<JobStatus, "kind">): boolean {
  return (job.kind ?? "ingest") === "ingest";
}

export interface JobStatus {
  job_id: string;
  /** What this job tracks (`ingest` | `metadata_sync` | `rebuild_index`). */
  kind: JobKindValue;
  /** The document the job works on — null for a collection-level job (`rebuild_index`). */
  document_id: string | null;
  /** The document's filename, joined at read — null only if the document row is gone. */
  document_filename: string | null;
  /** The document's metagen-generated title, joined at read — a nicer display label than the
   *  filename when present. Null if none was generated, the document is gone, or (SSE status
   *  frames only) the snapshot didn't re-join it — see streamJobEvents. */
  document_title: string | null;
  /** The document's display title (the collection's `title_field` value when set, else the parsed
   *  title). Null when neither exists, the document is gone, or on SSE status frames. */
  display_title?: string | null;
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
  /** The stage an ingest job replays from on the persisted IR (a `replay_from` reingest); absent/null
   *  for a full pipeline run. */
  replay_from?: string | null;
}

/** The one human label to show for a job, everywhere it's shown (job rows, worker cards, the job
 *  detail header): the display title (honours the collection's title field), else the metagen
 *  title, else the filename, else a generic fallback for the rare gone-document edge case. Keeping this in one place is what keeps the job
 *  list and the job detail header in sync. */
export function jobDisplayName(
  job: Pick<JobStatus, "display_title" | "document_title" | "document_filename"> & { kind?: JobKindValue },
): string {
  if (job.kind === "rebuild_index") return jobKindLabel(job.kind);
  return job.display_title || job.document_title || job.document_filename || "untitled document";
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
