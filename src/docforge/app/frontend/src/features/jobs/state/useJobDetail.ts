// ====== Code Summary ======
// All state/effects behind the job detail page: the collection's per-stage average durations (ETA
// basis), the live job feed (useJobFeed), the 5s re-render tick that keeps "elapsed in stage" live,
// and every value derived from that raw state (running-long flag, ETA, token totals, see
// jobDetailModel.ts) — extracted out of `JobDetailPage` so that component stays pure render.

import { useEffect, useState } from "react";
import { getStageDurations } from "../../../api/jobs";
import { deriveJobProgress, TERMINAL, toMonotonicTimeline } from "./jobDetailModel";
import { useJobFeed } from "./useJobFeed";

export function useJobDetail(jobId: string, collectionId: string) {
  const { job, events, error, live, patchJob } = useJobFeed(jobId);
  const [stageSeconds, setStageSeconds] = useState<Record<string, number>>({});

  // Per-stage averages across the collection's completed jobs — the ETA basis. Best-effort: a
  // failed fetch (or a collection with no history yet) just means no ETA is shown.
  useEffect(() => {
    getStageDurations(collectionId)
      .then((d) => setStageSeconds(d.stage_seconds))
      .catch(() => setStageSeconds({}));
  }, [collectionId]);

  // Re-render every 5s while running so an elapsed-in-stage computed from Date.now() (below)
  // doesn't freeze between status frames — needed for the "running long" flag to stay live.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!job || TERMINAL.has(job.status)) return;
    const id = window.setInterval(() => tick((n) => n + 1), 5000);
    return () => window.clearInterval(id);
  }, [job?.status]);

  if (!job) return { job: null, events, error, live, patchJob } as const;

  // Chronological + forward-corrected view used for every derived value below AND for render —
  // see toMonotonicTimeline for why the raw SSE-appended order can't be trusted as-is.
  const timeline = toMonotonicTimeline(events);
  const progress = deriveJobProgress(job, timeline, stageSeconds, Date.now());

  return { job, events: timeline, error, live, patchJob, ...progress } as const;
}
