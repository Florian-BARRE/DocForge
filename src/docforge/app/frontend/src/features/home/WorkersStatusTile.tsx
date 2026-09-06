// ====== Code Summary ======
// Home's worker-fleet tile: alive/busy/offline counts from the live worker feed, self-contained
// fetch+poll (mirrors WorkersPanel's own always-live pattern) so this tile works standalone even if
// a sibling Home tile's fetch fails.

import { useEffect, useState } from "react";
import { getWorkersLive, type WorkerActivity } from "../../api/jobs";
import { StatTile } from "../../components/StatTile";
import type { Navigate } from "../../shell/view";

const POLL_MS = 4000;

interface WorkersStatusTileProps {
  onNavigate: Navigate;
}

export function WorkersStatusTile({ onNavigate }: WorkersStatusTileProps) {
  const [workers, setWorkers] = useState<WorkerActivity[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      getWorkersLive()
        .then(({ workers: data }) => {
          if (cancelled) return;
          setWorkers(data);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch(() => {
          if (!cancelled) timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  if (!workers) return <StatTile value="…" label="Workers" />;

  const busyCount = workers.filter((w) => w.busy).length;
  const aliveCount = workers.filter((w) => w.alive).length;

  return (
    <StatTile
      value={`${busyCount}/${aliveCount}`}
      label="Busy / alive workers"
      tone={busyCount > 0 ? "accent" : "neutral"}
      caption={`${workers.length - aliveCount} offline`}
      onClick={() => onNavigate({ name: "workers" })}
    />
  );
}
