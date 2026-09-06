// ====== Code Summary ======
// The Monitoring page's main content — every worker's live CPU/memory/capacity readout, polled
// continuously (same cadence as the Workers page's WorkersPanel) so it reads as a real-time
// dashboard rather than a static snapshot. A small pulsing "live" affordance next to the section
// title makes that polling visible instead of implicit.

import { useEffect, useState } from "react";
import { getWorkersLive, type WorkerActivity } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";
import { WorkerLiveCard } from "./WorkerLiveCard";

const POLL_MS = 3000;

function LiveBadge() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: theme.font.size.xs, color: theme.color.dim }}>
      <span
        style={{
          width: 7, height: 7, borderRadius: theme.radius.pill, background: theme.color.accent,
          animation: "df-live-pulse 1.6s ease-in-out infinite",
        }}
      />
      updating live
      <style>
        {"@keyframes df-live-pulse { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } } "
          + "@media (prefers-reduced-motion: reduce) { [style*=\"df-live-pulse\"] { animation: none !important; } }"}
      </style>
    </span>
  );
}

export function LiveWorkersGrid() {
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
          // dashboard is always-live and has to recover on its own once the backend answers again.
          setError(e instanceof Error ? e.message : String(e));
          timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  return (
    <div style={{ marginBottom: theme.space.xl }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.m, marginBottom: theme.space.m }}>
        <span style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.xl, color: theme.color.text }}>
          Worker resources
        </span>
        <LiveBadge />
      </div>
      {error && <ErrorState message={error} />}
      {!error && !workers && <LoadingState label="loading fleet…" />}
      {!error && workers && workers.length === 0 && (
        <div
          style={{
            border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
            padding: theme.space.xxl, textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.l,
          }}
        >
          No worker has ever heartbeated.
        </div>
      )}
      {!error && workers && workers.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: theme.space.l }}>
          {workers.map((activity) => (
            <WorkerLiveCard key={activity.worker_id} activity={activity} />
          ))}
        </div>
      )}
    </div>
  );
}
