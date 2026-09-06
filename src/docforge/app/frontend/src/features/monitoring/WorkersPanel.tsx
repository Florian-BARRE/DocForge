// ====== Code Summary ======
// The fleet-wide live view: every worker with a RUNNING job, polled continuously while this
// page is open (there is no "settled" state for a fleet monitor — it is always live).

import { useEffect, useState } from "react";
import { getWorkersLive, type JobStatus, type WorkerActivity } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { RecentJobsPanel } from "./RecentJobsPanel";
import { WorkerCard } from "./WorkerCard";
import { WorkersFleetSummary } from "./WorkersFleetSummary";

const POLL_MS = 3000;

export function WorkersPanel({ onNavigate }: { onNavigate: Navigate }) {
  const [workers, setWorkers] = useState<WorkerActivity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      <PageHeader title="Workers" subtitle="Every worker process known to the fleet, live." />
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
              display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: theme.space.l,
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
    </div>
  );
}
