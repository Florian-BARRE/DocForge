// ====== Code Summary ======
// All state/effects behind the job detail page: the collection's per-stage average durations (ETA
// basis), the live SSE feed with poll fallback, a periodic full-trace reconciliation that corrects
// any stage the SSE delta cursor can't re-emit once finalized (see RECONCILE_MS), the 5s re-render
// tick that keeps "elapsed in stage" live, and every value derived from that raw state (running-long
// flag, ETA, token totals) — extracted out of `JobDetailPage` so that component stays pure render.

import { useCallback, useEffect, useState } from "react";
import { getJob, getJobTrace, getStageDurations, streamJobEvents, type JobEvent, type JobStatus } from "../../../api/jobs";

const POLL_MS = 2500;
const TERMINAL = new Set(["done", "failed", "cancelled"]);
// A running stage is flagged "running long" once its elapsed time crosses this multiple of the
// collection's own average for that stage — well before the 600s hard `stalled` flag.
const RUNNING_LONG_FACTOR = 2.5;
// How often the trace is re-fetched wholesale from GET /jobs/{id}/events while a job runs, ON TOP
// OF the SSE stream. The stream's delta cursor only counts newly-INSERTED rows: a root stage's
// event row is opened "running" at START and FINALIZED IN PLACE (same row) at END, so once its
// "running" frame has been emitted the finalized status is never re-sent over SSE — the trace would
// otherwise show that stage stuck "running" forever even after a downstream stage completes. This
// periodic reconciliation re-syncs the authoritative DB state so no stage's status goes stale.
const RECONCILE_MS = 4000;

/** Replace (by `stage`) or append one incoming event — keeps the timeline free of duplicate rows
 *  when the SSE stream and the reconciliation poll both observe the same stage. */
function upsertEvent(events: JobEvent[], incoming: JobEvent): JobEvent[] {
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
function toMonotonicTimeline(events: JobEvent[]): JobEvent[] {
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

export function useJobDetail(jobId: string, collectionId: string) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [stageSeconds, setStageSeconds] = useState<Record<string, number>>({});

  // Per-stage averages across the collection's completed jobs — the ETA basis. Best-effort: a
  // failed fetch (or a collection with no history yet) just means no ETA is shown.
  useEffect(() => {
    getStageDurations(collectionId)
      .then((d) => setStageSeconds(d.stage_seconds))
      .catch(() => setStageSeconds({}));
  }, [collectionId]);

  useEffect(() => {
    let cancelled = false;
    let pollTimer: number | undefined;
    const controller = new AbortController();

    // Fallback: the original poll loop — used only if the stream can't be opened/read.
    const startPolling = () => {
      const load = () => {
        Promise.all([getJob(jobId), getJobTrace(jobId)])
          .then(([jobData, traceData]) => {
            if (cancelled) return;
            setJob(jobData);
            setEvents(traceData.events);
            setError(null);
            if (jobData.status === "pending" || jobData.status === "running") pollTimer = window.setTimeout(load, POLL_MS);
          })
          .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
      };
      load();
    };

    // The SSE status snapshot is re-read from the job row alone (see stream_job_events) — it never
    // re-joins document_filename/document_title/collection_name, so a live-only session (no poll
    // fallback ever calling getJob) would show "untitled document" for the header until terminal.
    // One direct read seeds those joined identity fields up front; onStatus below preserves them
    // across every subsequent snapshot since they never change for a job's lifetime.
    getJob(jobId)
      .then((data) => {
        if (cancelled) return;
        setJob((prev) => (prev ? { ...prev, document_filename: data.document_filename, document_title: data.document_title, collection_name: data.collection_name } : data));
      })
      .catch(() => {});

    // Preferred: the live SSE stream. It replays the full event list on connect, then only the
    // delta — so appending each event is correct (no dedupe needed on a single connection).
    streamJobEvents(jobId, {
      signal: controller.signal,
      onStatus: (status) => {
        if (cancelled || status.status === "gone") return;
        setJob((prev) => ({
          ...status,
          document_filename: status.document_filename ?? prev?.document_filename ?? null,
          document_title: status.document_title ?? prev?.document_title ?? null,
          collection_name: status.collection_name ?? prev?.collection_name ?? null,
        }));
        setError(null);
        setLive(true);
      },
      onEvent: (event) => {
        if (cancelled) return;
        setEvents((prev) => upsertEvent(prev, event));
        setLive(true);
      },
    })
      .then(() => { if (!cancelled) setLive(false); })
      .catch(() => {
        // Stream unsupported / errored — reset any partial state and fall back to polling.
        if (cancelled || controller.signal.aborted) return;
        setLive(false);
        setEvents([]);
        startPolling();
      });

    return () => { cancelled = true; controller.abort(); window.clearTimeout(pollTimer); };
  }, [jobId]);

  // Belt-and-braces reconciliation against the authoritative trace endpoint (see RECONCILE_MS) —
  // keeps the SSE-driven timeline from ever showing a stage frozen "running" past its actual end.
  useEffect(() => {
    if (!job || TERMINAL.has(job.status)) return;
    let cancelled = false;
    const id = window.setInterval(() => {
      getJobTrace(jobId)
        .then((trace) => { if (!cancelled) setEvents(trace.events); })
        .catch(() => {});
    }, RECONCILE_MS);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [jobId, job?.status]);

  // Re-render every 5s while running so an elapsed-in-stage computed from Date.now() (below)
  // doesn't freeze between status frames — needed for the "running long" flag to stay live.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!job || TERMINAL.has(job.status)) return;
    const id = window.setInterval(() => tick((n) => n + 1), 5000);
    return () => window.clearInterval(id);
  }, [job?.status]);

  // Optimistic local patch after a cancel call — the SSE stream / poll will reconcile the rest,
  // but this makes the new status/cancel_requested show immediately instead of waiting a tick.
  const patchJob = useCallback((patch: Partial<JobStatus>) => {
    setJob((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  if (!job) return { job: null, events, error, live, patchJob } as const;

  const running = !TERMINAL.has(job.status);

  // Chronological + forward-corrected view used for every derived value below AND for render —
  // see toMonotonicTimeline for why the raw SSE-appended order can't be trusted as-is.
  const timeline = toMonotonicTimeline(events);

  // The currently-open trace row for the active stage (worker writes it on START) gives the real
  // stage-start time — elapsed-in-stage vs. the collection average is the "running long" signal.
  const activeStageEvent = job.current_stage
    ? [...timeline].reverse().find((e) => e.stage === job.current_stage && e.started_at && !e.finished_at)
    : undefined;
  const elapsedInStageSeconds =
    running && activeStageEvent?.started_at
      ? (Date.now() - new Date(activeStageEvent.started_at).getTime()) / 1000
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
    timeline.filter((e) => TERMINAL.has(e.status) || e.status === "skipped").map((e) => e.stage),
  );
  const etaSeconds = running
    ? Object.entries(stageSeconds)
        .filter(([stage]) => !finishedStages.has(stage))
        .reduce((sum, [, seconds]) => sum + seconds, 0)
    : 0;
  const totalTokens = job.total_prompt_tokens + job.total_completion_tokens;

  return {
    job, events: timeline, error, live, patchJob,
    running, elapsedInStageSeconds, avgStageSeconds, runningLong, etaSeconds, totalTokens,
  } as const;
}
