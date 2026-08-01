// ====== Code Summary ======
// One job's compact summary row — reused by both JobsPage (a collection's jobs) and WorkerCard
// (a worker's currently running jobs), since both work off the same JobStatus shape.

import { useState } from "react";
import type { JobStatus } from "../../api/jobs";
import { theme } from "../../theme";
import { JobStatusChip } from "./JobStatusChip";
import { ProgressBar } from "./ProgressBar";

interface JobRowProps {
  job: JobStatus;
  onClick: () => void;
}

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function idleFor(updatedAt: string): string {
  const minutes = Math.floor((Date.now() - new Date(updatedAt).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`;
}

export function JobRow({ job, onClick }: JobRowProps) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: theme.color.surface, border: `1px solid ${hover ? theme.color.accentLine : theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m, cursor: "pointer",
        display: "flex", flexDirection: "column", gap: theme.space.s,
        boxShadow: hover ? theme.shadow.md : theme.shadow.sm,
        transform: hover ? "translateY(-1px)" : "none",
        transition: "transform .15s ease, box-shadow .15s ease, border-color .15s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.dim }}>{job.job_id.slice(0, 8)}</span>
        <JobStatusChip status={job.status} />
        {job.stalled && (
          <span
            title={`No progress since ${formatTimestamp(job.updated_at)} — the worker reaper will fail it if it stays wedged.`}
            style={{
              color: theme.color.warn, background: theme.color.warnSoft,
              fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold,
              padding: "1px 7px", borderRadius: theme.radius.pill, border: `1px solid ${theme.color.warn}`,
            }}
          >
            stalled · idle {idleFor(job.updated_at)}
          </span>
        )}
        {job.current_stage && (
          <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>stage: {job.current_stage}</span>
        )}
        <span style={{ marginLeft: "auto", color: theme.color.dim, fontSize: theme.font.size.xs }}>
          attempt {job.attempt}
        </span>
      </div>
      <ProgressBar progress={job.progress} status={job.status} />
      <div style={{ display: "flex", justifyContent: "space-between", color: theme.color.dim, fontSize: theme.font.size.xs }}>
        <span>started: {formatTimestamp(job.started_at)}</span>
        <span>finished: {formatTimestamp(job.finished_at)}</span>
      </div>
      {job.error && <div style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{job.error}</div>}
    </div>
  );
}
