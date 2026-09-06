// ====== Code Summary ======
// Job-level fleet monitoring (NOT host CPU/mem — that's the optional telemetry overlay, see
// TelemetryNote): fleet queue depth + a coarse throughput figure, the pointer to the full Grafana
// board for anyone who needs host metrics too, and a recent-completed-jobs list so the page reads
// as a real monitor rather than stopping at two tiles. A per-collection cost tile was scoped but
// SKIPPED here (getCollectionCost has no fleet-wide variant — summing it across every collection
// client-side risks a slow page on a large fleet; see the agent report's out-of-scope note).

import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
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
      <PageHeader title="Monitoring" subtitle="Job-level fleet health." />

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l, marginBottom: theme.space.l }}>
        <QueueDepthTile />
        <ThroughputTile />
      </div>

      <div style={{ marginBottom: theme.space.xl }}>
        <TelemetryNote />
      </div>

      <RecentJobsPanel
        title="Recent completed jobs"
        status={["done"]}
        emptyLabel="No completed jobs yet."
        onNavigate={onNavigate}
      />
    </div>
  );
}
