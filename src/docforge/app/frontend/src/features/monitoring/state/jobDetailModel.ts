// ====== Code Summary ======
// Pure model of the job detail page (useJobDetail / useJobFeed): the terminal-status set, the
// timeline normalisation (dedupe-by-stage upsert, chronological order, forward-corrected stale
// "running" rows) and every value derived from the job + timeline (running-long flag, ETA, token
// totals). No React, no I/O — `now` is passed in.

import type { JobEvent, JobStatus } from "../../../api/jobs";

export const TERMINAL = new Set(["done", "failed", "cancelled"]);
// A per-stage trace EVENT's `status` mirrors the engine's NodeStatus ("success" | "failed" |
// "skipped"; "running" while the stage is still open) — a DIFFERENT enum from the job-level
// JobStatusValue above ("pending" | "running" | "done" | "failed" | "cancelled"). Reusing TERMINAL
// against event.status only ever matched "failed", so a successfully-finished stage was never
// counted as done and the ETA never shrank as the job progressed.
const EVENT_FINISHED = new Set(["success", "failed", "skipped"]);
// A running stage is flagged "running long" once its elapsed time crosses this multiple of the
// collection's own average for that stage — well before the 600s hard `stalled` flag.
const RUNNING_LONG_FACTOR = 2.5;

/** Replace (by `stage`) or append one incoming event — keeps the timeline free of duplicate rows
 *  when the SSE stream and the reconciliation poll both observe the same stage. */
export function upsertEvent(events: JobEvent[], incoming: JobEvent): JobEvent[] {
  const index = events.findIndex((e) => e.stage === incoming.stage);
  if (index === -1) return [...events, incoming];
  const next = [...events];
  next[index] = incoming;
  return next;
}

/**
 * Sort the trace chronologically and forward-correct any stage still showing "running" once a later
 * (later-`started_at`) stage has itself started — a sequential pipeline can't have started a
 * downstream stage without finishing the upstream one, so that "running" is stale SSE data (the
 * finalize-in-place update the delta cursor can't re-emit, per the module comment above). Smooths the
 * transient non-monotone flash in the first seconds after submit until RECONCILE_MS corrects it for real.
 */
export function toMonotonicTimeline(events: JobEvent[]): JobEvent[] {
  const ordered = [...events].sort((a, b) => {
    const aTime = a.started_at ? new Date(a.started_at).getTime() : Number.MAX_SAFE_INTEGER;
    const bTime = b.started_at ? new Date(b.started_at).getTime() : Number.MAX_SAFE_INTEGER;
    return aTime - bTime;
  });
  let downstreamStarted = false;
  for (let i = ordered.length - 1; i >= 0; i--) {
    const event = ordered[i];
    if (downstreamStarted && event.status === "running") ordered[i] = { ...event, status: "success" };
    if (event.started_at) downstreamStarted = true;
  }
  return ordered;
}

export interface JobProgress {
  running: boolean;
  elapsedInStageSeconds: number | null;
  avgStageSeconds: number | undefined;
  runningLong: boolean;
  etaSeconds: number;
  totalTokens: number;
}

/** Everything the page derives from the job row, its (normalised) timeline and the stage averages. */
export function deriveJobProgress(
  job: JobStatus,
  timeline: JobEvent[],
  stageSeconds: Record<string, number>,
  now: number,
): JobProgress {
  const running = !TERMINAL.has(job.status);

  // The currently-open trace row for the active stage (worker writes it on START) gives the real
  // stage-start time — elapsed-in-stage vs. the collection average is the "running long" signal.
  const activeStageEvent = job.current_stage
    ? [...timeline].reverse().find((e) => e.stage === job.current_stage && e.started_at && !e.finished_at)
    : undefined;
  const elapsedInStageSeconds =
    running && activeStageEvent?.started_at
      ? (now - new Date(activeStageEvent.started_at).getTime()) / 1000
      : null;
  const avgStageSeconds = job.current_stage ? stageSeconds[job.current_stage] : undefined;
  const runningLong =
    running &&
    elapsedInStageSeconds !== null &&
    avgStageSeconds !== undefined &&
    avgStageSeconds > 0 &&
    elapsedInStageSeconds > avgStageSeconds * RUNNING_LONG_FACTOR;

  // ETA: sum the collection-average durations of the stages this running job hasn't finished yet.
  const finishedStages = new Set(
    timeline.filter((e) => EVENT_FINISHED.has(e.status)).map((e) => e.stage),
  );
  const etaSeconds = running
    ? Object.entries(stageSeconds)
        .filter(([stage]) => !finishedStages.has(stage))
        .reduce((sum, [, seconds]) => sum + seconds, 0)
    : 0;
  const totalTokens = job.total_prompt_tokens + job.total_completion_tokens;

  return { running, elapsedInStageSeconds, avgStageSeconds, runningLong, etaSeconds, totalTokens };
}
