// ====== Code Summary ======
// Fleet-wide header stats for the Workers page — totals across every known worker: alive vs
// offline, busy vs idle, and aggregate running-job capacity (summed only across workers that
// actually reported a capacity). Purely derived from the same WorkerActivity list WorkersPanel
// already polls; no extra fetch.

import type { WorkerActivity } from "../../api/jobs";
import { StatTile } from "../../components/StatTile";
import { theme } from "../../theme";

interface WorkersFleetSummaryProps {
  workers: WorkerActivity[];
}

export function WorkersFleetSummary({ workers }: WorkersFleetSummaryProps) {
  const alive = workers.filter((w) => w.alive);
  const busy = alive.filter((w) => w.busy);
  const idle = alive.length - busy.length;
  const offline = workers.length - alive.length;

  const running = workers.reduce((sum, w) => sum + w.jobs.length, 0);
  // `max_jobs` null (an old heartbeat row) is excluded from the sum rather than counted as 0 — the
  // total must never understate the fleet's real configured capacity.
  const withKnownCapacity = workers.filter((w) => w.max_jobs !== null);
  const capacity = withKnownCapacity.reduce((sum, w) => sum + (w.max_jobs ?? 0), 0);
  const unknownCapacityCount = workers.length - withKnownCapacity.length;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l, marginBottom: theme.space.xl }}>
      <StatTile value={alive.length} label="Alive" tone="ok" />
      <StatTile value={busy.length} label="Busy" tone={busy.length > 0 ? "accent" : "neutral"} />
      <StatTile value={idle} label="Idle" tone="neutral" />
      <StatTile value={offline} label="Offline" tone={offline > 0 ? "warn" : "neutral"} />
      <StatTile
        value={`${running} / ${capacity}`}
        label="Fleet capacity"
        tone="neutral"
        caption={
          unknownCapacityCount > 0
            ? `running / configured (${unknownCapacityCount} unknown)`
            : "running / configured"
        }
      />
    </div>
  );
}
