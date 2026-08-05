// ====== Code Summary ======
// One job's full detail: header (status, progress, attempt, timestamps) + its per-node trace as a
// vertical timeline. Consumes the live SSE feed (GET /jobs/{id}/stream) — status snapshots update
// the header/progress in real time and stage events append to the timeline as they land, closing at
// terminal. The API is header-only auth (EventSource can't set the Bearer), so the stream is read
// via fetch + ReadableStream (see api/jobs.streamJobEvents). If the stream errors or is unsupported,
// it falls back to the original ~2.5s poll of getJob + getJobTrace.

import { useEffect, useState } from "react";
import { getJob, getJobTrace, getStageDurations, streamJobEvents, type JobEvent, type JobStatus } from "../../api/jobs";
import { BackLink } from "../../components/BackLink";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { FailedNodeBreadcrumb } from "./FailedNodeBreadcrumb";
import { ItemProgressChip } from "./ItemProgressChip";
import { JobEventItem } from "./JobEventItem";
import { JobStatusChip } from "./JobStatusChip";
import { ProgressBar } from "./ProgressBar";

const POLL_MS = 2500;
const TERMINAL = new Set(["done", "failed"]);
// A running stage is flagged "running long" once its elapsed time crosses this multiple of the
// collection's own average for that stage — well before the 600s hard `stalled` flag.
const RUNNING_LONG_FACTOR = 2.5;

interface JobDetailPageProps {
  jobId: string;
  collectionId: string;
  onNavigate: Navigate;
}

export function JobDetailPage({ jobId, collectionId, onNavigate }: JobDetailPageProps) {
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

  if (error) return <ErrorState message={error} />;
  if (!job) return <LoadingState label="loading job…" />;

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

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        eyebrow={<BackLink label="Jobs" onClick={() => onNavigate({ name: "collection-jobs", collectionId })} />}
        title={<span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xxl }}>{job.job_id}</span>}
        subtitle={
          <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            <span>document {job.document_id} · attempt {job.attempt}</span>
            <JobStatusChip status={job.status} />
            {live && running && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs, color: theme.color.accent, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold }}>
                <span style={{ width: 7, height: 7, borderRadius: theme.radius.pill, background: theme.color.accent }} />
                live
              </span>
            )}
          </span>
        }
      />

      <div
        style={{
          background: theme.color.surface, border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
          marginBottom: theme.space.l,
        }}
      >
        <ProgressBar progress={job.progress} status={job.status} />
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.l, color: theme.color.dim, fontSize: theme.font.size.s, marginTop: theme.space.s, flexWrap: "wrap" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
            stage: {job.current_stage ?? "—"}
            {job.items_done !== null && job.items_total !== null && (
              <ItemProgressChip itemsDone={job.items_done} itemsTotal={job.items_total} />
            )}
          </span>
          <span>started: {job.started_at ? new Date(job.started_at).toLocaleString() : "—"}</span>
          <span>finished: {job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}</span>
          {running && etaSeconds > 0 && (
            <span style={{ color: theme.color.accent, fontWeight: theme.font.weight.semibold }}>
              ~{etaSeconds < 90 ? `${Math.round(etaSeconds)}s` : `${Math.round(etaSeconds / 60)}m`} remaining
            </span>
          )}
          {runningLong && (
            <Chip
              tone="warn"
              title={`Elapsed ${Math.round(elapsedInStageSeconds!)}s in "${job.current_stage}" vs. a ~${Math.round(avgStageSeconds!)}s collection average — may be wedged.`}
            >
              running long
            </Chip>
          )}
        </div>
        {totalTokens > 0 && (
          <div style={{ display: "flex", gap: theme.space.l, marginTop: theme.space.s, fontFamily: theme.font.mono, fontSize: theme.font.size.s }}>
            <span title="Prompt + completion tokens billed across this document's paid model calls." style={{ color: theme.color.text }}>
              {totalTokens.toLocaleString()} tokens
            </span>
            <span title="Total USD cost of this document's paid calls." style={{ color: theme.color.accent, fontWeight: theme.font.weight.semibold }}>
              ${job.cost_usd.toFixed(4)}
            </span>
            <span style={{ color: theme.color.mute }}>
              ({job.total_prompt_tokens.toLocaleString()} in · {job.total_completion_tokens.toLocaleString()} out)
            </span>
          </div>
        )}
        {job.error && (
          <div style={{ marginTop: theme.space.s }}>
            <FailedNodeBreadcrumb job={job} />
            <div
              style={{
                color: job.failed_node_id ? theme.color.dim : theme.color.error,
                fontSize: theme.font.size.xs,
                marginTop: job.failed_node_id ? theme.space.xs : 0,
              }}
            >
              {job.error}
            </div>
          </div>
        )}
      </div>

      <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.l, fontWeight: 600, color: theme.color.text, marginBottom: theme.space.m }}>
        Trace
      </h2>
      {events.length === 0 && <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No stage events yet.</div>}
      {events.length > 0 && (
        <div
          style={{
            background: theme.color.surface, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: `${theme.space.m}px ${theme.space.l}px`,
          }}
        >
          {events.map((event, index) => <JobEventItem key={index} event={event} />)}
        </div>
      )}
    </div>
  );
}
