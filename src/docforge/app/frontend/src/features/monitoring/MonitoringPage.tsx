// ====== Code Summary ======
// A REAL live worker dashboard: a compact top row (fleet queue depth + throughput), then the main
// content — every worker's live CPU/memory/capacity readout (LiveWorkersGrid, polled) — followed by
// a recent-completed-jobs list. Host-level metrics (disk, long-range trends) are demoted to a small
// footnote (TelemetryNote) pointing at the optional Grafana overlay — no longer the page's main
// content, since live worker resources now render in-product. A per-collection cost tile was scoped
// but SKIPPED here (getCollectionCost has no fleet-wide variant — summing it across every collection
// client-side risks a slow page on a large fleet; see the agent report's out-of-scope note).

import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { LiveWorkersGrid } from "./LiveWorkersGrid";
import { QueueDepthTile } from "./QueueDepthTile";
import { RecentJobsPanel } from "./RecentJobsPanel";
import { TelemetryNote } from "./TelemetryNote";
import { ThroughputTile } from "./ThroughputTile";

interface MonitoringPageProps {
  onNavigate: Navigate;
}

export function MonitoringPage({ onNavigate }: MonitoringPageProps) {
  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader title="Monitoring" subtitle="Live worker resources + job-level fleet health." />

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l, marginBottom: theme.space.xl }}>
        <QueueDepthTile />
        <ThroughputTile />
      </div>

      <LiveWorkersGrid />

      <div style={{ marginBottom: theme.space.xl }}>
        <RecentJobsPanel
          title="Recent completed jobs"
          status={["done"]}
          emptyLabel="No completed jobs yet."
          onNavigate={onNavigate}
        />
      </div>

      <TelemetryNote />
    </div>
  );
}
