// ====== Code Summary ======
// Full-page host for the collection import bundle picker — reachable from the sidebar's
// Collections › Import destination. Thin composition: page chrome + the existing `ImportPanel`
// (previously only ever shown inline under the fleet list's toolbar).

import { BackLink } from "../../components/BackLink";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { ImportPanel } from "./transfer/ImportPanel";

interface ImportCollectionPageProps {
  onNavigate: Navigate;
}

export function ImportCollectionPage({ onNavigate }: ImportCollectionPageProps) {
  return (
    <div className="df-rise" style={{ padding: `${theme.space.xl}px`, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        eyebrow={<BackLink label="Collections" onClick={() => onNavigate({ name: "collections" })} />}
        title="Import collection"
        subtitle="Restore a portable .dcexport bundle produced by another DocForge server."
      />
      <div style={{ marginTop: theme.space.l }}>
        <ImportPanel onNavigate={onNavigate} />
      </div>
    </div>
  );
}
