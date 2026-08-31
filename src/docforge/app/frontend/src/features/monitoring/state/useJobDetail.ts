// ====== Code Summary ======
// All state/effects behind the job detail page: the collection's per-stage average durations (ETA
// basis), the live SSE feed with poll fallback, the 5s re-render tick that keeps "elapsed in
// stage" live, and every value derived from that raw state (running-long flag, ETA, token totals)
// — extracted out of `JobDetailPage` so that component stays pure render.

import { useCallback, useEffect, useState } from "react";
import { getJob, getJobTrace, getStageDurations, streamJobEvents, type JobEvent, type JobStatus } from "../../../api/jobs";

const POLL_MS = 2500;
const TERMINAL = new Set(["done", "failed", "cancelled"]);
// A running stage is flagged "running long" once its elapsed time crosses this multiple of the
// collection's own average for that stage — well before the 600s hard `stalled` flag.
const RUNNING_LONG_FACTOR = 2.5;

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

    // Preferred: the live SSE stream. It replays the full event list on connect, then only the
    // delta — so appending each event is correct (no dedupe needed on a single connection).
    streamJobEvents(jobId, {
      signal: controller.signal,
      onStatus: (status) => {
        if (cancelled || status.status === "gone") return;
        setJob(status);
        setError(null);
        setLive(true);
      },
      onEvent: (event) => {
        if (cancelled) return;
        setEvents((prev) => [...prev, event]);
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

  // The currently-open trace row for the active stage (worker writes it on START) gives the real
  // stage-start time — elapsed-in-stage vs. the collection average is the "running long" signal.
  const activeStageEvent = job.current_stage
    ? [...events].reverse().find((e) => e.stage === job.current_stage && e.started_at && !e.finished_at)
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
    events.filter((e) => TERMINAL.has(e.status) || e.status === "skipped").map((e) => e.stage),
  );
  const etaSeconds = running
    ? Object.entries(stageSeconds)
        .filter(([stage]) => !finishedStages.has(stage))
        .reduce((sum, [, seconds]) => sum + seconds, 0)
    : 0;
  const totalTokens = job.total_prompt_tokens + job.total_completion_tokens;

  return {
    job, events, error, live, patchJob,
    running, elapsedInStageSeconds, avgStageSeconds, runningLong, etaSeconds, totalTokens,
  } as const;
}
