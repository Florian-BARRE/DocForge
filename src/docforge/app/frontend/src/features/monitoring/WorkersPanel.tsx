// ====== Code Summary ======
// The fleet-wide live view: every worker with a RUNNING job, polled continuously while this page is
// open (there is no "settled" state for a fleet monitor — it is always live). Also folds in what
// used to be the separate Monitoring page: a top throughput tile above the fleet summary, and a
// telemetry footnote below the recent-activity panel — the former Monitoring page's live-per-worker
// grid (LiveWorkersGrid/WorkerLiveCard) was a strict SUBSET of the WorkerCard grid already rendered
// here, so it was deleted rather than folded in (see agent-memory/frontend for the consolidation
// note). Fleet-wide QUEUE DEPTH moved to Activity ▸ Trends (IA redesign W3) — it's a job-flow signal,
// not a worker one, and duplicating the same tile on both pages was exactly the redundancy the
// redesign set out to kill; Fleet keeps throughput (a worker-capacity signal proper to this page). A
// compact top-right toggle switches the card grid between list/grid-N/auto layouts via the shared
// ViewModeToggle, persisted per-viewer (useViewMode, storage key docforge_view_workers).

import { useEffect, useState } from "react";
import { getWorkersLive, type JobStatus, type WorkerActivity } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { gridTemplateColumnsFor, useViewMode } from "../../components/viewMode/useViewMode";
import { ViewModeToggle } from "../../components/viewMode/ViewModeToggle";
import { TopContentBar } from "../../shell/TopContentBar";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { RecentJobsPanel } from "./RecentJobsPanel";
import { TelemetryNote } from "./TelemetryNote";
import { ThroughputTile } from "./ThroughputTile";
import { WorkerCard } from "./WorkerCard";
import { WorkersFleetSummary } from "./WorkersFleetSummary";

const POLL_MS = 3000;
const GRID_MIN_PX = 320;

export function WorkersPanel({ onNavigate }: { onNavigate: Navigate }) {
  const [workers, setWorkers] = useState<WorkerActivity[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { mode, setMode } = useViewMode("docforge_view_workers");

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      getWorkersLive()
        .then(({ workers: data }) => {
          if (cancelled) return;
          setWorkers(data);
          setError(null);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch((e) => {
          if (cancelled) return;
          // A transient poll failure surfaces the error but must NOT kill the interval — the
          // fleet view is always-live and has to recover on its own once the backend answers again.
          setError(e instanceof Error ? e.message : String(e));
          timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  // Applied right after a cancel/stop/force call resolves, so the affected job's card reflects the
  // new state immediately rather than waiting for the next poll tick.
  const updateJob = (jobId: string, patch: Partial<JobStatus>) => {
    setWorkers((prev) =>
      prev
        ? prev.map((w) => ({ ...w, jobs: w.jobs.map((j) => (j.job_id === jobId ? { ...j, ...patch } : j)) }))
        : prev,
    );
  };

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <TopContentBar
        page="Fleet"
        subtitle="Live worker resources, queue depth, and fleet health."
        actions={<ViewModeToggle mode={mode} onChange={setMode} label="Workers" />}
        onNavigate={onNavigate}
      />

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l, marginBottom: theme.space.xl }}>
        <ThroughputTile />
      </div>

      {error && <ErrorState message={error} />}
      {!error && !workers && <LoadingState label="loading fleet…" />}
      {workers && workers.length === 0 && (
        <div
          style={{
            border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
            padding: theme.space.xxl, textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.l,
            marginBottom: theme.space.xl,
          }}
        >
          No worker has ever heartbeated.
        </div>
      )}
      {workers && workers.length > 0 && (
        <>
          <WorkersFleetSummary workers={workers} />
          <div
            style={{
              display: "grid", gridTemplateColumns: gridTemplateColumnsFor(mode, GRID_MIN_PX), gap: theme.space.l,
              marginBottom: theme.space.xl,
            }}
          >
            {workers.map((activity) => (
              <WorkerCard key={activity.worker_id} activity={activity} onNavigate={onNavigate} onJobUpdated={updateJob} />
            ))}
          </div>
        </>
      )}
      {!error && workers && (
        <RecentJobsPanel
          title="Recent activity across the fleet"
          status={["running", "done"]}
          emptyLabel="No running or completed jobs yet."
          onNavigate={onNavigate}
        />
      )}

      <div style={{ marginTop: theme.space.xl }}>
        <TelemetryNote />
      </div>
    </div>
  );
}
