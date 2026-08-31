// ====== Code Summary ======
// A thin horizontal progress bar (0-100) for a transfer, colored by its status — same visual
// language as the monitoring feature's job ProgressBar, kept as a local copy per this codebase's
// feature-slice-isolation convention (features never cross-import each other).

import { theme } from "../../../theme";
import type { TransferStatusValue } from "../../../api/transfers";

const COLOR_BY_STATUS: Record<string, string> = {
  failed: theme.color.error,
  done: theme.color.ok,
};

export function TransferProgressBar({ progress, status }: { progress: number; status: TransferStatusValue }) {
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
