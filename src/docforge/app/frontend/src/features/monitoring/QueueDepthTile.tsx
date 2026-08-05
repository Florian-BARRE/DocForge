// ====== Code Summary ======
// "N pending / M running" backlog tile for a collection's JobsPage — polls GET /jobs/queue while
// mounted so backlog building up (uploads outrunning the worker) is visible before it becomes a
// stall. Self-contained polling: independent of the jobs-list poll it sits above.

import { useEffect, useState } from "react";
import { getQueueDepth, type QueueDepth } from "../../api/jobs";
import { theme } from "../../theme";

const POLL_MS = 3000;

interface QueueDepthTileProps {
  collectionId: string;
}

export function QueueDepthTile({ collectionId }: QueueDepthTileProps) {
  const [depth, setDepth] = useState<QueueDepth | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      getQueueDepth(collectionId)
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
  }, [collectionId]);

  if (!depth) return null;

  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: theme.space.xl,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm,
        padding: `${theme.space.s}px ${theme.space.l}px`, marginBottom: theme.space.l,
      }}
    >
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        <span
          style={{
            fontFamily: theme.font.mono, fontSize: theme.font.size.xl, fontWeight: theme.font.weight.semibold,
            color: depth.pending > 0 ? theme.color.warn : theme.color.text, marginRight: theme.space.xs,
          }}
        >
          {depth.pending}
        </span>
        pending
      </span>
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        <span
          style={{
            fontFamily: theme.font.mono, fontSize: theme.font.size.xl, fontWeight: theme.font.weight.semibold,
            color: depth.running > 0 ? theme.color.accent : theme.color.text, marginRight: theme.space.xs,
          }}
        >
          {depth.running}
        </span>
        running
      </span>
    </div>
  );
}
