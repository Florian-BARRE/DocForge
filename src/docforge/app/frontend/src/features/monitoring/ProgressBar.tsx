// ====== Code Summary ======
// A thin horizontal progress bar (0-100), colored by the job's status — the same visual
// language across JobRow, JobDetailPage and WorkerCard.

import { theme } from "../../theme";
import type { JobStatusValue } from "../../api/jobs";

const COLOR_BY_STATUS: Record<string, string> = {
  failed: theme.color.error,
  done: theme.color.ok,
};

export function ProgressBar({ progress, status }: { progress: number; status: JobStatusValue }) {
  const color = COLOR_BY_STATUS[status] ?? theme.color.accent;
  return (
    <div style={{ background: theme.color.surface2, borderRadius: theme.radius.pill, height: 6, overflow: "hidden" }}>
      <div
        style={{
          width: `${Math.max(0, Math.min(100, progress))}%`, height: "100%", borderRadius: theme.radius.pill,
          background: color, transition: "width .3s ease",
        }}
      />
    </div>
  );
}
