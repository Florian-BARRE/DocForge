// ====== Code Summary ======
// The in-shell Settings page — ONE rail entry whose equal-depth sub-tabs (rendered by CollectionShell's
// CollectionSubNav, routed via the View's `section`) each show ONLY their own content: General (the
// identity/schema/review edit wizard, embedded — see CollectionWizard's `mode === "edit"` branch — with
// the Danger zone at the bottom), Aliases (AliasesPanel), History (history/ConfigHistoryPanel) and
// Transfer (ExportPanel: export the collection or a config slice, apply an inbound snippet). Fetches the
// collection once and hands it to the wizard (as `initial`) and the panels that need its name — a page
// remount (e.g. returning from a save) always refetches it.

import { useEffect, useState } from "react";
import { getCollection, type Collection } from "../../../api/collections";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import type { CollectionSettingsSection, Navigate } from "../../../shell/view";
import { theme } from "../../../theme";
import { ConfigHistoryPanel } from "../history/ConfigHistoryPanel";
import { ExportPanel } from "../transfer/ExportPanel";
import { AliasesPanel } from "./AliasesPanel";
import { CollectionWizard } from "../wizard/CollectionWizard";
import { DangerZone } from "./DangerZone";
import { SettingsSection } from "./SettingsSection";

interface CollectionSettingsPageProps {
  collectionId: string;
  section: CollectionSettingsSection;
  onNavigate: Navigate;
}

export function CollectionSettingsPage({ collectionId, section, onNavigate }: CollectionSettingsPageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getCollection(collectionId)
      .then(setCollection)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [collectionId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  return (
    <div
      className="df-rise"
      style={{
        padding: theme.space.xl, maxWidth: 1200, margin: "0 auto", overflowY: "auto", height: "100%",
        display: "flex", flexDirection: "column", gap: theme.space.xxl,
      }}
    >
      {section === "general" && (
        <>
          <SettingsSection
            title="Contract"
            description="Identity, formats, size cap, timeout, trace verbosity and tags — schema fields are managed on the Schema tab."
          >
            <CollectionWizard mode="edit" collectionId={collectionId} initial={collection} onNavigate={onNavigate} />
          </SettingsSection>
          <SettingsSection title="Danger zone">
            <DangerZone collectionId={collectionId} collectionName={collection.name} onNavigate={onNavigate} />
          </SettingsSection>
        </>
      )}

      {section === "aliases" && (
        <SettingsSection
          title="Aliases"
          description="Stable names usable in place of this collection's id (and as an alias:<name> key scope). Switching an alias here moves every client and alias-scoped key to this collection."
        >
          <AliasesPanel collectionId={collectionId} collectionName={collection.name} />
        </SettingsSection>
      )}

      {section === "history" && (
        <SettingsSection
          title="History"
          description="Every pipeline/search config change, who made it and what it changed — compare two versions or restore one (a restore writes a new version)."
        >
          <ConfigHistoryPanel collectionId={collectionId} />
        </SettingsSection>
      )}

      {section === "transfer" && (
        <SettingsSection
          title="Transfer"
          description="Export this collection (or a single config slice) for reuse elsewhere, or apply an inbound config snippet."
        >
          <ExportPanel collectionId={collectionId} collectionName={collection.name} />
        </SettingsSection>
      )}
    </div>
  );
}
