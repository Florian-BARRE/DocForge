// ====== Code Summary ======
// The fleet-wide live view: every worker with a RUNNING job, polled continuously while this
// page is open (there is no "settled" state for a fleet monitor — it is always live).

import { useEffect, useState } from "react";
import { getWorkersLive, type WorkerActivity } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
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

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <h1 style={{ fontSize: theme.font.size.xl, marginBottom: theme.space.l }}>Workers</h1>
      {error && <ErrorState message={error} />}
      {!error && !workers && <LoadingState label="loading fleet…" />}
      {workers && workers.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>Fleet idle — no worker has a running job.</div>
      )}
      {workers && workers.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: theme.space.m }}>
          {workers.map((activity) => <WorkerCard key={activity.worker_id} activity={activity} onNavigate={onNavigate} />)}
        </div>
      )}
    </div>
  );
}
