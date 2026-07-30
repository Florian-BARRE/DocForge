// ====== Code Summary ======
// TypeScript mirror of the jobs (ingestion monitoring) REST contract + its typed client.

import { apiFetch } from "./http";

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
