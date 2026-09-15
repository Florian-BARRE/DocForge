// ====== Code Summary ======
// The consolidated in-shell Settings page (replaces the old standalone edit route) — three clearly
// labeled sections stacked on one scrollable page: Contract (the existing identity/schema/review
// edit wizard, embedded — see CollectionWizard's `mode === "edit"` branch), Transfer (export the
// whole collection or a config snippet, and apply an inbound snippet — ExportPanel already covers
// both), and Danger zone (delete + full reingest). Fetches the collection once and hands it to
// both the wizard (as `initial`) and the two other sections (name only) — a page remount (e.g.
// returning from a save) always refetches it.

import { useEffect, useState } from "react";
import { getCollection, type Collection } from "../../../api/collections";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import type { Navigate } from "../../../shell/view";
import { theme } from "../../../theme";
import { ExportPanel } from "../transfer/ExportPanel";
import { CollectionWizard } from "../wizard/CollectionWizard";
import { DangerZone } from "./DangerZone";
import { SettingsSection } from "./SettingsSection";

interface CollectionSettingsPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionSettingsPage({ collectionId, onNavigate }: CollectionSettingsPageProps) {
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
      <SettingsSection
        title="Contract"
        description="Identity, formats, size cap, timeout, trace verbosity and tags — schema fields are managed on the Schema tab."
      >
        <CollectionWizard mode="edit" collectionId={collectionId} initial={collection} onNavigate={onNavigate} />
      </SettingsSection>

      <SettingsSection
        title="Transfer"
        description="Export this collection (or a single config slice) for reuse elsewhere, or apply an inbound config snippet."
      >
        <ExportPanel collectionId={collectionId} collectionName={collection.name} />
      </SettingsSection>

      <SettingsSection title="Danger zone">
        <DangerZone collectionId={collectionId} collectionName={collection.name} onNavigate={onNavigate} />
      </SettingsSection>
    </div>
  );
}
