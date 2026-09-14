// ====== Code Summary ======
// Status-to-tone mapping for both a job's own status (pending/running/done/failed) and a job
// stage event's status string — a shared primitive (components/trace/) used by the monitoring
// feature (JobRow, JobDetailPage) and JobEventItem, which the document explorer's Trace tab
// also renders.

import { Chip, type ChipTone } from "../../components/Chip";

const TONE_BY_STATUS: Record<string, ChipTone> = {
  pending: "warn",
  queued: "warn",
  running: "accent",
  done: "ok",
  success: "ok",
  failed: "error",
  error: "error",
  skipped: "dim",
  cancelled: "skip",
};

export function JobStatusChip({ status }: { status: string }) {
  return <Chip tone={TONE_BY_STATUS[status] ?? "dim"}>{status}</Chip>;
}
