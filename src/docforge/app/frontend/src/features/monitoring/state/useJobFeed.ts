// ====== Code Summary ======
// The live feed of one job: the SSE stream with poll fallback (job row + trace events), plus a
// periodic full-trace reconciliation that corrects any stage the SSE delta cursor can't re-emit once
// finalized (see RECONCILE_MS). Extracted from useJobDetail; the timeline maths is in jobDetailModel.ts.

import { useCallback, useEffect, useState } from "react";
import { getJob, getJobTrace, streamJobEvents, type JobEvent, type JobStatus } from "../../../api/jobs";
import { TERMINAL, upsertEvent } from "./jobDetailModel";

const POLL_MS = 2500;
// How often the trace is re-fetched wholesale from GET /jobs/{id}/events while a job runs, ON TOP
// OF the SSE stream. The stream's delta cursor only counts newly-INSERTED rows: a root stage's
// event row is opened "running" at START and FINALIZED IN PLACE (same row) at END, so once its
// "running" frame has been emitted the finalized status is never re-sent over SSE — the trace would
// otherwise show that stage stuck "running" forever even after a downstream stage completes. This
// periodic reconciliation re-syncs the authoritative DB state so no stage's status goes stale.
const RECONCILE_MS = 4000;

export function useJobFeed(jobId: string) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);

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

  // Optimistic local patch after a cancel call — the SSE stream / poll will reconcile the rest,
  // but this makes the new status/cancel_requested show immediately instead of waiting a tick.
  const patchJob = useCallback((patch: Partial<JobStatus>) => {
    setJob((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  return { job, events, error, live, patchJob };
}
