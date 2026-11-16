// ====== Code Summary ======
// Home's worker-fleet tile: alive/busy/offline counts from the live worker feed, self-contained
// fetch+poll (mirrors WorkersPanel's own always-live pattern) so this tile works standalone even if
// a sibling Home tile's fetch fails.

import { useState } from "react";
import { getWorkersLive, type WorkerActivity } from "../../api/jobs";
import { StatTile } from "../../components/StatTile";
import { usePolling } from "../../hooks/usePolling";
import { useNavigate } from "../../shell/navigation";

const POLL_MS = 4000;

export function WorkersStatusTile() {
  const navigate = useNavigate();
  const [workers, setWorkers] = useState<WorkerActivity[] | null>(null);

  usePolling(
    () => getWorkersLive(),
    { intervalMs: POLL_MS, onData: ({ workers: data }) => setWorkers(data) },
    [],
  );

  if (!workers) return <StatTile value="…" label="Workers" />;

  const busyCount = workers.filter((w) => w.busy).length;
  const aliveCount = workers.filter((w) => w.alive).length;

  return (
    <StatTile
      value={`${busyCount}/${aliveCount}`}
      label="Busy / alive workers"
      tone={busyCount > 0 ? "accent" : "neutral"}
      caption={`${workers.length - aliveCount} offline`}
      onClick={() => navigate({ name: "fleet" })}
    />
  );
}
