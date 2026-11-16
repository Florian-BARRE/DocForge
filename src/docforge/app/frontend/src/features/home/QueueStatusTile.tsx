// ====== Code Summary ======
// Overview's queue/workers cockpit tile — the fleet-wide backlog, self-contained fetch+poll. A LINK
// card (not a raw duplicate): the queue/workers surface as a whole routes to Fleet (grouped with
// WorkersStatusTile, its sibling tile) per the IA redesign — the detailed backlog TREND lives on
// Activity ▸ Trends instead, closing the QueueDepthTile duplication the redesign set out to kill.

import { useState } from "react";
import { getQueueDepth, type QueueDepth } from "../../api/jobs";
import { StatTile } from "../../components/StatTile";
import { usePolling } from "../../hooks/usePolling";
import { useNavigate } from "../../shell/navigation";

const POLL_MS = 5000;

export function QueueStatusTile() {
  const navigate = useNavigate();
  const [depth, setDepth] = useState<QueueDepth | null>(null);

  usePolling(
    () => getQueueDepth(),
    { intervalMs: POLL_MS, onData: setDepth },
    [],
  );

  if (!depth) return <StatTile value="…" label="Pending jobs" />;

  return (
    <StatTile
      value={depth.pending}
      label="Pending jobs"
      tone={depth.pending > 0 ? "warn" : "neutral"}
      caption={`${depth.running} running — see Fleet`}
      onClick={() => navigate({ name: "fleet" })}
    />
  );
}
