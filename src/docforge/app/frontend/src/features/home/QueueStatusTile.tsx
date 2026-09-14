// ====== Code Summary ======
// Overview's queue/workers cockpit tile — the fleet-wide backlog, self-contained fetch+poll. A LINK
// card (not a raw duplicate): the queue/workers surface as a whole routes to Fleet (grouped with
// WorkersStatusTile, its sibling tile) per the IA redesign — the detailed backlog TREND lives on
// Activity ▸ Trends instead, closing the QueueDepthTile duplication the redesign set out to kill.

import { useEffect, useState } from "react";
import { getQueueDepth, type QueueDepth } from "../../api/jobs";
import { StatTile } from "../../components/StatTile";
import type { Navigate } from "../../shell/view";

const POLL_MS = 5000;

interface QueueStatusTileProps {
  onNavigate: Navigate;
}

export function QueueStatusTile({ onNavigate }: QueueStatusTileProps) {
  const [depth, setDepth] = useState<QueueDepth | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      getQueueDepth()
        .then((data) => {
          if (cancelled) return;
          setDepth(data);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch(() => {
          if (!cancelled) timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  if (!depth) return <StatTile value="…" label="Pending jobs" />;

  return (
    <StatTile
      value={depth.pending}
      label="Pending jobs"
      tone={depth.pending > 0 ? "warn" : "neutral"}
      caption={`${depth.running} running — see Fleet`}
      onClick={() => onNavigate({ name: "fleet" })}
    />
  );
}
