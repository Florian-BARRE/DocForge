// ====== Code Summary ======
// The Overview's ingestion-jobs synthesis — status counts, the currently in-flight jobs with
// their progress, the most recent failures, and the last activity timestamp. Degrades to a calm
// empty state when the collection has never run a job, and never dumps an unbounded list — capped
// sections always say "+N more" instead of silently truncating.

import type { DocumentListItem } from "../../api/explorer";
import type { JobStatus, JobStatusValue } from "../../api/jobs";
import { Button } from "../../components/Button";
import { Chip, type ChipTone } from "../../components/Chip";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import { Row, SummaryCard } from "./OverviewCardPrimitives";
import { humanizeRelativeTime } from "./relativeTime";

const MAX_ROWS_SHOWN = 5;
const MAX_FAILED_SHOWN = 3;
const TONE_BY_STATUS: Record<string, ChipTone> = { running: "accent", pending: "warn", done: "ok", failed: "error" };

interface JobsSummaryCardProps {
  jobs: JobStatus[] | null;
  docs: DocumentListItem[] | null;
  collectionId: string;
  onNavigate: Navigate;
}

function isActive(job: JobStatus): boolean {
  return job.status === "running" || job.status === "pending";
}

/** Per-status counts as Chips, hiding zero-count statuses. */
function StatusCounts({ jobs }: { jobs: JobStatus[] }) {
  const counts: Record<string, number> = {};
  for (const j of jobs) counts[j.status] = (counts[j.status] ?? 0) + 1;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {(Object.keys(counts) as JobStatusValue[]).map((status) => (
        <Chip key={status} tone={TONE_BY_STATUS[status] ?? "dim"}>{counts[status]} {status}</Chip>
      ))}
    </div>
  );
}

/** One in-flight job — its current stage and a slim progress bar. */
function InFlightRow({ job, label }: { job: JobStatus; label: string }) {
  const pct = Math.max(0, Math.min(100, job.progress));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: t.font.size.s, color: t.color.dim }}>
        <span>{label} · {job.current_stage ?? "…"}</span>
        <span>{Math.round(pct)}%</span>
      </div>
      <div style={{ background: t.color.surface2, borderRadius: t.radius.pill, height: 5, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: t.radius.pill, background: t.color.accent }} />
      </div>
    </div>
  );
}

/** One failed job — its truncated error message, clickable through to the job's detail page. */
function FailedRow({ job, label, onClick }: { job: JobStatus; label: string; onClick: () => void }) {
  const message = job.error ? (job.error.length > 90 ? `${job.error.slice(0, 90)}…` : job.error) : "no error message recorded";
  return (
    <div onClick={onClick} style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: t.font.size.s, color: t.color.dim }}>{label}</span>
      <span style={{ fontSize: t.font.size.s, color: t.color.error }}>{message}</span>
    </div>
  );
}

export function JobsSummaryCard({ jobs, docs, collectionId, onNavigate }: JobsSummaryCardProps) {
  const open = () => onNavigate({ name: "collection-jobs", collectionId });
  const filenameById = new Map((docs ?? []).map((d) => [d.id, d.filename] as const));
  const labelFor = (job: JobStatus) => filenameById.get(job.document_id) ?? job.document_id.slice(0, 8);

  if (jobs === null) {
    return <SummaryCard title="Ingestion jobs" onOpen={open}><span style={{ color: t.color.dim, fontSize: t.font.size.m }}>loading…</span></SummaryCard>;
  }
  if (jobs.length === 0) {
    return (
      <SummaryCard title="Ingestion jobs" onOpen={open}>
        <span style={{ color: t.color.dim, fontSize: t.font.size.m }}>No ingestion runs yet — upload a document to see one here.</span>
      </SummaryCard>
    );
  }

  // 1. In-flight jobs, most recently started first, capped so the card never grows unbounded.
  const active = jobs.filter(isActive).sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
  const activeShown = active.slice(0, MAX_ROWS_SHOWN);

  // 2. Failures, most recently finished first.
  const failed = jobs.filter((j) => j.status === "failed").sort((a, b) => (b.finished_at ?? "").localeCompare(a.finished_at ?? ""));
  const failedShown = failed.slice(0, MAX_FAILED_SHOWN);

  // 3. Last activity across the whole batch — finished_at if the job settled, else started_at.
  const lastTimestamp = jobs.map((j) => j.finished_at ?? j.started_at).filter((v): v is string => !!v).sort().pop() ?? null;

  // 4. Ingestion spend rolled up across every job (re-ingests included — it's a true spend meter).
  const spendUsd = jobs.reduce((sum, j) => sum + (j.cost_usd ?? 0), 0);
  const spendTokens = jobs.reduce((sum, j) => sum + j.total_prompt_tokens + j.total_completion_tokens, 0);

  return (
    <SummaryCard title="Ingestion jobs" onOpen={open}>
      <StatusCounts jobs={jobs} />

      {activeShown.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: t.space.s }}>
          {activeShown.map((j) => <InFlightRow key={j.job_id} job={j} label={labelFor(j)} />)}
          {active.length > activeShown.length && (
            <span style={{ color: t.color.dim, fontSize: t.font.size.xs }}>+{active.length - activeShown.length} more running</span>
          )}
        </div>
      )}

      {failed.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: t.space.s }}>
          {failedShown.map((j) => (
            <FailedRow key={j.job_id} job={j} label={labelFor(j)} onClick={() => onNavigate({ name: "job", collectionId, jobId: j.job_id })} />
          ))}
          {failed.length > failedShown.length && (
            <span style={{ color: t.color.dim, fontSize: t.font.size.xs }}>+{failed.length - failedShown.length} more failed</span>
          )}
        </div>
      )}

      <Row label="Last activity" value={humanizeRelativeTime(lastTimestamp)} />
      {spendTokens > 0 && (
        <Row
          label="Ingestion spend"
          value={
            <span style={{ fontFamily: t.font.mono }}>
              <span style={{ color: t.color.accent, fontWeight: t.font.weight.semibold }}>${spendUsd.toFixed(4)}</span>
              <span style={{ color: t.color.mute }}> · {spendTokens.toLocaleString()} tok</span>
            </span>
          }
        />
      )}
      <div><Button size="sm" variant="secondary" onClick={open}>Open Jobs →</Button></div>
    </SummaryCard>
  );
}
