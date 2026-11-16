// ====== Code Summary ======
// "Jobs done in the last hour" — a coarse fleet throughput signal. There is no dedicated throughput
// endpoint, so this reads the most recent DONE jobs (newest-first, server-clamped page) and counts
// how many finished within the trailing window client-side — an approximation, not an exact rate,
// documented here rather than silently presented as precise.

import { useState } from "react";
import { listJobsPage } from "../../api/jobs";
import { StatTile } from "../../components/StatTile";
import { usePolling } from "../../hooks/usePolling";

const POLL_MS = 5000;
const WINDOW_MINUTES = 60;
// Recent-DONE jobs fetched to scan for the window count — generous enough that a busy fleet's last
// hour is unlikely to be truncated, without asking the server for anywhere near JOBS_MAX_PAGE_SIZE.
const SCAN_LIMIT = 100;

function countWithinWindow(finishedAtValues: (string | null)[], windowMinutes: number): number {
  const cutoff = Date.now() - windowMinutes * 60_000;
  return finishedAtValues.filter((value) => value !== null && new Date(value).getTime() >= cutoff).length;
}

export function ThroughputTile() {
  const [count, setCount] = useState<number | null>(null);

  usePolling(
    () => listJobsPage({ status: ["done"], order: "newest", limit: SCAN_LIMIT }),
    { intervalMs: POLL_MS, onData: (page) => setCount(countWithinWindow(page.jobs.map((j) => j.finished_at), WINDOW_MINUTES)) },
    [],
  );

  return (
    <StatTile
      value={count ?? "…"}
      label={`Done in the last ${WINDOW_MINUTES}m`}
      tone="ok"
      caption={`of the last ${SCAN_LIMIT} completed jobs scanned`}
    />
  );
}
