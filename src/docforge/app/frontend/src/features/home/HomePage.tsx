// ====== Code Summary ======
// The default landing page — a fleet-wide "step back and manage" dashboard. Big-number tiles ONLY
// for the figures that are the point (collections needing attention/operational, worker busy/alive,
// queue depth); everything else (the recent-failures strip) stays quiet body content. Each tile/
// section owns its own fetch+poll, so one failing probe never blocks the rest of the page.

import { QueueDepthTile } from "../monitoring/QueueDepthTile";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { CollectionsStatusTiles } from "./CollectionsStatusTiles";
import { RecentFailuresStrip } from "./RecentFailuresStrip";
import { WorkersStatusTile } from "./WorkersStatusTile";

interface HomePageProps {
  onNavigate: Navigate;
}

export function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader title="Home" subtitle="The fleet at a glance." />

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l, marginBottom: theme.space.xl }}>
        <CollectionsStatusTiles onNavigate={onNavigate} />
        <WorkersStatusTile onNavigate={onNavigate} />
        <QueueDepthTile />
      </div>

      <RecentFailuresStrip onNavigate={onNavigate} />
    </div>
  );
}
