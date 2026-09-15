// ====== Code Summary ======
// Overview's recent-failures cockpit tile — a LINK card, not a duplicate list: the canonical failure
// forensics (breakdown by cause/stage/collection, the recently-failed list) now live on Activity ▸
// Failures. This tile only summarizes the rolling-window failure count and routes there, replacing
// the old RecentFailuresStrip (which re-rendered a full JobRow list — a second copy of that surface).

import { useEffect, useState } from "react";
import { getFailureBreakdown, type FailureBreakdown } from "../../api/jobs";
import { StatTile } from "../../components/StatTile";
import type { Navigate } from "../../shell/view";

const POLL_MS = 15000;
const WINDOW_HOURS = 24;

interface RecentFailuresTileProps {
  onNavigate: Navigate;
}

export function RecentFailuresTile({ onNavigate }: RecentFailuresTileProps) {
  const [data, setData] = useState<FailureBreakdown | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      getFailureBreakdown({ windowHours: WINDOW_HOURS })
        .then((next) => {
          if (cancelled) return;
          setData(next);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch(() => {
          if (!cancelled) timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  if (!data) return <StatTile value="…" label="Recent failures" />;

  return (
    <StatTile
      value={data.total_failed}
      label="Recent failures"
      tone={data.total_failed > 0 ? "error" : "ok"}
      caption={`last ${data.window_hours}h — see Activity ▸ Failures`}
      onClick={() => onNavigate({ name: "activity", tab: "failures" })}
    />
  );
}
