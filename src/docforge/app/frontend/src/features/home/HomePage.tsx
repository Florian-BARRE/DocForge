// ====== Code Summary ======
// The default landing page — a lean fleet cockpit: SUMMARY + LINK tiles only, never a re-rendering
// of a page it links to (IA redesign W3). Collections status routes into Collections' health presets;
// workers/queue both route into Fleet; recent failures routes into Activity ▸ Failures. Each tile
// owns its own fetch+poll, so one failing probe never blocks the rest of the page.

import { Button } from "../../components/Button";
import { TopContentBar } from "../../shell/TopContentBar";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { CollectionsStatusTiles } from "./CollectionsStatusTiles";
import { QueueStatusTile } from "./QueueStatusTile";
import { RecentFailuresTile } from "./RecentFailuresTile";
import { WorkersStatusTile } from "./WorkersStatusTile";

interface HomePageProps {
  onNavigate: Navigate;
}

export function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <TopContentBar
        page="Overview"
        subtitle="The fleet at a glance — every tile routes into its own canonical page for the detail."
        actions={<Button variant="primary" onClick={() => onNavigate({ name: "new-collection" })}>+ New collection</Button>}
        onNavigate={onNavigate}
      />

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l }}>
        <CollectionsStatusTiles onNavigate={onNavigate} />
        <WorkersStatusTile onNavigate={onNavigate} />
        <QueueStatusTile onNavigate={onNavigate} />
        <RecentFailuresTile onNavigate={onNavigate} />
      </div>
    </div>
  );
}
