// ====== Code Summary ======
// TypeScript mirror of the jobs (ingestion monitoring) REST contract + its typed client.

import { apiFetch, clearApiToken, getApiToken, HttpError } from "./http";

const BASE = "/api/v1/jobs";

// Mirrors the backend's JobStatus StrEnum verbatim (`pending`, not `queued`) — the `| string`
// fallback keeps this open to a future status without breaking the build.
export type JobStatusValue = "pending" | "running" | "done" | "failed" | string;

export interface JobStatus {
  job_id: string;
  document_id: string;
  collection_id: string;
  status: JobStatusValue;
  progress: number;
  current_stage: string | null;
  error: string | null;
  attempt: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobEvent {
  stage: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  detail: string | null;
}

export interface JobTrace {
  job_id: string;
  events: JobEvent[];
}

export interface WorkerActivity {
  worker_id: string;
  jobs: JobStatus[];
}

export interface WorkersLive {
  workers: WorkerActivity[];
}

export function listJobs(collectionId: string): Promise<JobStatus[]> {
  return apiFetch(`${BASE}?collection_id=${encodeURIComponent(collectionId)}`);
}

export function getJob(jobId: string): Promise<JobStatus> {
  return apiFetch(`${BASE}/${jobId}`);
}

export function getJobTrace(jobId: string): Promise<JobTrace> {
  return apiFetch(`${BASE}/${jobId}/events`);
}

export function getWorkersLive(): Promise<WorkersLive> {
  return apiFetch(`${BASE}/workers/live`);
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
