// ====== Code Summary ======
// A thin horizontal progress bar (0-100), colored by the job's status — the same visual
// language across JobRow, JobDetailPage and WorkerCard. The forge accent (the brand's ONE
// "active work" signal, see brand.md) only ever fills the bar for a still-running/pending job —
// every terminal status renders in its own status ink, never accent: `failed`/`cancelled` must
// never read as "the thing being worked" once the job is over.

import { theme } from "../../theme";
import type { JobStatusValue } from "../../api/jobs";

const COLOR_BY_STATUS: Record<string, string> = {
  failed: theme.color.error,
  done: theme.color.ok,
  cancelled: theme.color.skip,
};

// `cancelled` additionally gets the brand's "deliberate stop" hatch (see Chip's `skip` tone —
// dashed, never a plain solid fill) instead of a solid bar: a full solid fill reads as "actively
// filling" regardless of hue, which is the wrong affordance for a job that was stopped, not one
// that failed mid-work.
function fillFor(status: JobStatusValue): string {
  const color = COLOR_BY_STATUS[status] ?? theme.color.accent;
  if (status !== "cancelled") return color;
  return `repeating-linear-gradient(45deg, ${color}, ${color} 4px, transparent 4px, transparent 8px)`;
}

export function ProgressBar({ progress, status }: { progress: number; status: JobStatusValue }) {
  return (
    <div style={{ background: theme.color.surface2, borderRadius: theme.radius.pill, height: 6, overflow: "hidden" }}>
      <div
        style={{
          width: `${Math.max(0, Math.min(100, progress))}%`, height: "100%", borderRadius: theme.radius.pill,
          background: fillFor(status), transition: "width .3s ease",
        }}
      />
    </div>
  );
}
