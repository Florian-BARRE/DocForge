// ====== Code Summary ======
// One job's compact summary row — reused by both JobsPage (a collection's jobs) and WorkerCard
// (a worker's currently running jobs), since both work off the same JobStatus shape.

import { useState } from "react";
import type { JobStatus } from "../../api/jobs";
import { theme } from "../../theme";
import { ItemProgressChip } from "./ItemProgressChip";
import { JobCancelControl } from "./JobCancelControl";
import { JobIdentity } from "./JobIdentity";
import { JobStatusChip } from "./JobStatusChip";
import { ProgressBar } from "./ProgressBar";

interface JobRowProps {
  job: JobStatus;
  onClick: () => void;
  /** Applied to the row's own job when a cancel/stop/force call resolves — lets the parent's list
   *  reflect the new state immediately. */
  onUpdated: (patch: Partial<JobStatus>) => void;
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

export function JobRow({ job, onClick, onUpdated }: JobRowProps) {
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
      <div style={{ display: "flex", alignItems: "flex-start", gap: theme.space.s }}>
        <JobIdentity job={job} />
        <div style={{ marginLeft: "auto", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "flex-end", gap: theme.space.xs }}>
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
          {job.items_done !== null && job.items_total !== null && (
            <ItemProgressChip itemsDone={job.items_done} itemsTotal={job.items_total} />
          )}
          <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>attempt {job.attempt}</span>
          <JobCancelControl job={job} onUpdated={onUpdated} />
        </div>
      </div>
      <ProgressBar progress={job.progress} status={job.status} />
      <div style={{ display: "flex", justifyContent: "space-between", color: theme.color.dim, fontSize: theme.font.size.xs }}>
        <span>started: {formatTimestamp(job.started_at)}</span>
        <span>finished: {formatTimestamp(job.finished_at)}</span>
      </div>
      {job.error && (
        <div style={{ color: job.status === "failed" ? theme.color.error : theme.color.skip, fontSize: theme.font.size.xs }}>
          {job.error}
        </div>
      )}
    </div>
  );
}
