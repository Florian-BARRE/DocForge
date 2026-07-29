// ====== Code Summary ======
// One job's full detail: header (status, progress, attempt, timestamps) + its per-node trace
// as a vertical timeline. Polls both the job and its trace while the job is still in flight.

import { useEffect, useState } from "react";
import { getJob, getJobTrace, type JobStatus, type JobTrace } from "../../api/jobs";
import { BackLink } from "../../components/BackLink";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { JobEventItem } from "./JobEventItem";
import { JobStatusChip } from "./JobStatusChip";
import { ProgressBar } from "./ProgressBar";

const POLL_MS = 2500;

interface JobDetailPageProps {
  jobId: string;
  collectionId: string;
  onNavigate: Navigate;
}

export function JobDetailPage({ jobId, collectionId, onNavigate }: JobDetailPageProps) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [trace, setTrace] = useState<JobTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      Promise.all([getJob(jobId), getJobTrace(jobId)])
        .then(([jobData, traceData]) => {
          if (cancelled) return;
          setJob(jobData);
          setTrace(traceData);
          setError(null);
          if (jobData.status === "pending" || jobData.status === "running") timer = window.setTimeout(load, POLL_MS);
        })
        .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [jobId]);

  if (error) return <ErrorState message={error} />;
  if (!job || !trace) return <LoadingState label="loading job…" />;

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        eyebrow={<BackLink label="Jobs" onClick={() => onNavigate({ name: "collection-jobs", collectionId })} />}
        title={<span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xxl }}>{job.job_id}</span>}
        subtitle={
          <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            <span>document {job.document_id} · attempt {job.attempt}</span>
            <JobStatusChip status={job.status} />
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
        <div style={{ display: "flex", gap: theme.space.l, color: theme.color.dim, fontSize: theme.font.size.s, marginTop: theme.space.s }}>
          <span>started: {job.started_at ? new Date(job.started_at).toLocaleString() : "—"}</span>
          <span>finished: {job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}</span>
        </div>
        {job.error && (
          <div style={{ color: theme.color.error, fontSize: theme.font.size.s, marginTop: theme.space.s }}>{job.error}</div>
        )}
      </div>

      <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.l, fontWeight: 600, color: theme.color.text, marginBottom: theme.space.m }}>
        Trace
      </h2>
      {trace.events.length === 0 && <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No stage events yet.</div>}
      {trace.events.length > 0 && (
        <div
          style={{
            background: theme.color.surface, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: `${theme.space.m}px ${theme.space.l}px`,
          }}
        >
          {trace.events.map((event, index) => <JobEventItem key={index} event={event} />)}
        </div>
      )}
    </div>
  );
}
