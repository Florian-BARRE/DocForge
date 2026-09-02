// ====== Code Summary ======
// One job's full detail: header (status, progress, attempt, timestamps) + its per-node trace as a
// vertical timeline. Consumes the live SSE feed (GET /jobs/{id}/stream) — status snapshots update
// the header/progress in real time and stage events append to the timeline as they land, closing at
// terminal. The API is header-only auth (EventSource can't set the Bearer), so the stream is read
// via fetch + ReadableStream (see api/jobs.streamJobEvents). If the stream errors or is unsupported,
// it falls back to the original ~2.5s poll of getJob + getJobTrace. All of that — plus every
// derived metric (ETA, running-long, token totals) — lives in `useJobDetail`; the summary card is
// `JobSummaryCard`. This component is pure top-level layout.

import { jobDisplayName } from "../../api/jobs";
import { BackLink } from "../../components/BackLink";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { JobCancelControl } from "./JobCancelControl";
import { JobEventItem } from "./JobEventItem";
import { JobStatusChip } from "./JobStatusChip";
import { JobSummaryCard } from "./JobSummaryCard";
import { useJobDetail } from "./state/useJobDetail";

interface JobDetailPageProps {
  jobId: string;
  collectionId: string;
  onNavigate: Navigate;
}

export function JobDetailPage({ jobId, collectionId, onNavigate }: JobDetailPageProps) {
  const detail = useJobDetail(jobId, collectionId);

  if (detail.error) return <ErrorState message={detail.error} />;
  if (!detail.job) return <LoadingState label="loading job…" />;
  const { job, events, live, running, patchJob, etaSeconds, runningLong, elapsedInStageSeconds, avgStageSeconds, totalTokens } = detail;

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        eyebrow={<BackLink label="Jobs" onClick={() => onNavigate({ name: "collection-jobs", collectionId })} />}
        title={<span>{jobDisplayName(job)}</span>}
        subtitle={
          <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            {job.collection_name && <span>{job.collection_name}</span>}
            <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.mute }}>job {job.job_id}</span>
            <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.mute }}>doc {job.document_id}</span>
            <span>attempt {job.attempt}</span>
            <JobStatusChip status={job.status} />
            {live && running && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs, color: theme.color.accentSafe, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold }}>
                <span style={{ width: 7, height: 7, borderRadius: theme.radius.pill, background: theme.color.accent }} />
                live
              </span>
            )}
            <JobCancelControl job={job} onUpdated={patchJob} />
          </span>
        }
      />

      <JobSummaryCard
        job={job}
        running={running}
        etaSeconds={etaSeconds}
        runningLong={runningLong}
        elapsedInStageSeconds={elapsedInStageSeconds}
        avgStageSeconds={avgStageSeconds}
        totalTokens={totalTokens}
      />

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
