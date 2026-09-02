// ====== Code Summary ======
// The job detail page's top card: progress bar, stage/ETA/timestamps line, token+cost totals (when
// any paid calls ran), and the failed-node breadcrumb + error text (when the job failed). Pure
// render over the metrics `useJobDetail` derives — no state of its own.

import type { JobStatus } from "../../api/jobs";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";
import { FailedNodeBreadcrumb } from "./FailedNodeBreadcrumb";
import { ItemProgressChip } from "./ItemProgressChip";
import { ProgressBar } from "./ProgressBar";
import { humanizeStageId } from "./stageLabels";

interface JobSummaryCardProps {
  job: JobStatus;
  running: boolean;
  etaSeconds: number;
  runningLong: boolean;
  elapsedInStageSeconds: number | null;
  avgStageSeconds: number | undefined;
  totalTokens: number;
}

export function JobSummaryCard({
  job, running, etaSeconds, runningLong, elapsedInStageSeconds, avgStageSeconds, totalTokens,
}: JobSummaryCardProps) {
  const stageLabel = job.current_stage ? humanizeStageId(job.current_stage) : null;
  return (
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
          <span title={job.current_stage ?? undefined}>stage: {stageLabel ?? "—"}</span>
          {job.items_done !== null && job.items_total !== null && (
            <ItemProgressChip itemsDone={job.items_done} itemsTotal={job.items_total} />
          )}
        </span>
        <span>started: {job.started_at ? new Date(job.started_at).toLocaleString() : "—"}</span>
        <span>finished: {job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}</span>
        {running && etaSeconds > 0 && (
          <span style={{ color: theme.color.accentSafe, fontWeight: theme.font.weight.semibold }}>
            ~{etaSeconds < 90 ? `${Math.round(etaSeconds)}s` : `${Math.round(etaSeconds / 60)}m`} remaining
          </span>
        )}
        {runningLong && (
          <Chip
            tone="warn"
            title={`Elapsed ${Math.round(elapsedInStageSeconds!)}s in "${stageLabel}" vs. a ~${Math.round(avgStageSeconds!)}s collection average — may be wedged.`}
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
          <span title="Total USD cost of this document's paid calls." style={{ color: theme.color.accentSafe, fontWeight: theme.font.weight.semibold }}>
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
              // A cancelled job's `error` is just the cancellation detail, not a failure — never the
              // error-red token for it (brand.md: cancelled reads as a deliberate stop, not a failure).
              color: job.status !== "failed" ? theme.color.skip : job.failed_node_id ? theme.color.dim : theme.color.error,
              fontSize: theme.font.size.xs,
              marginTop: job.failed_node_id ? theme.space.xs : 0,
            }}
          >
            {job.error}
          </div>
        </div>
      )}
    </div>
  );
}
