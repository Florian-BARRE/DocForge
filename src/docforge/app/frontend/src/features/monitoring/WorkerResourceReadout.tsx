// ====== Code Summary ======
// A worker's live CPU + memory readout — two ResourceBars fed by the heartbeat's sampled psutil
// figures. `cpu_percent`/`mem_mb`/`mem_percent` are each independently nullable (an old heartbeat
// row, a non-sampling build, or a first unprimed tick) — rendered as "not reported", never a
// fabricated number. Shared by WorkerLiveCard (Monitoring page) and WorkerCard (Workers page) so
// both surfaces agree on the same readout.

import type { WorkerActivity } from "../../api/jobs";
import { ResourceBar } from "./ResourceBar";

// A percent metric's natural 100%-fill reference; CPU legitimately exceeds it on a multi-core host.
const PERCENT_MAX = 100;

export function WorkerResourceReadout({ activity }: { activity: WorkerActivity }) {
  const memLabel = activity.mem_mb !== null ? `Memory · ${activity.mem_mb.toFixed(0)} MB` : "Memory";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <ResourceBar
        label="CPU"
        value={activity.cpu_percent}
        max={PERCENT_MAX}
        formatValue={(v) => `${v.toFixed(1)}%`}
      />
      <ResourceBar
        label={memLabel}
        value={activity.mem_percent}
        max={PERCENT_MAX}
        formatValue={(v) => `${v.toFixed(1)}%`}
      />
    </div>
  );
}
