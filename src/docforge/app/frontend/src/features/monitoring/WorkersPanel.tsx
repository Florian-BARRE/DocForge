// ====== Code Summary ======
// The fleet-wide live view: every worker with a RUNNING job, polled continuously while this
// page is open (there is no "settled" state for a fleet monitor — it is always live).

import { useEffect, useState } from "react";
import { getWorkersLive, type WorkerActivity } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { WorkerCard } from "./WorkerCard";

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
        .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  const busyCount = workers?.filter((w) => w.busy).length ?? 0;
  const aliveCount = workers?.filter((w) => w.alive).length ?? 0;
  const idleCount = aliveCount - busyCount;
  const offlineCount = (workers?.length ?? 0) - aliveCount;

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        title="Workers"
        subtitle={
          workers
            ? `${busyCount} busy · ${idleCount} idle · ${offlineCount} offline (${workers.length} worker${workers.length === 1 ? "" : "s"} known)`
            : " "
        }
      />
      {error && <ErrorState message={error} />}
      {!error && !workers && <LoadingState label="loading fleet…" />}
      {workers && workers.length === 0 && (
        <div
          style={{
            border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
            padding: theme.space.xxl, textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.l,
          }}
        >
          No worker has ever heartbeated.
        </div>
      )}
      {workers && workers.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: theme.space.l }}>
          {workers.map((activity) => <WorkerCard key={activity.worker_id} activity={activity} onNavigate={onNavigate} />)}
        </div>
      )}
    </div>
  );
}
