// ====== Code Summary ======
// Overview cockpit panel — the last handful of fleet-wide jobs (newest first), each row linking
// straight into that job's detail. A LINK-through glance (capped rows), never a duplicate of the
// full Activity ▸ Jobs table; self-contained fetch+poll so one failing probe never blocks a sibling
// Overview panel/tile.

import { useEffect, useState } from "react";
import { jobDisplayName, listJobsPage, type JobStatus } from "../../api/jobs";
import { JobStatusChip } from "../../components/trace/JobStatusChip";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";

const POLL_MS = 10000;
const MAX_ROWS = 6;

// Tiny local humanizer, deliberately duplicated rather than cross-imported — see
// agent-memory/frontend/feature_slice_isolation.md.
function humanizeAgo(iso: string): string {
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (deltaSeconds < 60) return "just now";
  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;
  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;
  return `${Math.floor(deltaHours / 24)}d ago`;
}

interface RecentActivityRowProps {
  job: JobStatus;
  onNavigate: Navigate;
}

function RecentActivityRow({ job, onNavigate }: RecentActivityRowProps) {
  const go = () => onNavigate({ name: "job", collectionId: job.collection_id, jobId: job.job_id });
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={go}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }}
      style={{
        display: "flex", flexDirection: "column", gap: 2, padding: `${theme.space.xs}px ${theme.space.s}px`,
        borderRadius: theme.radius.m, cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.s }}>
        <span style={{ color: theme.color.text, fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, overflowWrap: "anywhere" }}>
          {jobDisplayName(job)}
        </span>
        <JobStatusChip status={job.status} />
      </div>
      <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>
        {job.collection_name ?? "unknown collection"} · <span style={{ fontFamily: theme.font.mono }}>{humanizeAgo(job.updated_at)}</span>
      </span>
    </div>
  );
}

interface RecentActivityPanelProps {
  onNavigate: Navigate;
}

export function RecentActivityPanel({ onNavigate }: RecentActivityPanelProps) {
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      listJobsPage({ limit: MAX_ROWS, order: "newest" })
        .then((page) => {
          if (cancelled) return;
          setJobs(page.jobs);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch(() => {
          if (!cancelled) timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  return (
    <div
      style={{
        flex: 1, minWidth: 320, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
        background: theme.color.surface, padding: theme.space.l, display: "flex", flexDirection: "column", gap: theme.space.s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.l, color: theme.color.text }}>
          Recent activity
        </span>
        <button
          type="button"
          onClick={() => onNavigate({ name: "activity", tab: "jobs" })}
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: theme.color.accentSafe, fontSize: theme.font.size.xs, textDecoration: "underline" }}
        >
          View all in Activity
        </button>
      </div>

      {!jobs ? (
        <span style={{ color: theme.color.mute, fontSize: theme.font.size.s }}>Loading recent jobs…</span>
      ) : jobs.length === 0 ? (
        <span style={{ color: theme.color.mute, fontSize: theme.font.size.s }}>No jobs have run yet.</span>
      ) : (
        jobs.map((job) => <RecentActivityRow key={job.job_id} job={job} onNavigate={onNavigate} />)
      )}
    </div>
  );
}
