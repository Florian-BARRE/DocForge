// ====== Code Summary ======
// The landing page: every collection as a fleet-dashboard card (name, live health, doc/chunk counts,
// last ingest, parser), with a search/sort/health-filter toolbar above the grid, "New collection" to
// open the wizard, and click a card to open its detail page. State (list load, per-card health/doc-
// count fan-out, search/sort/filter) lives in useCollectionsFleet.

import { useState } from "react";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { CollectionCard } from "./CollectionCard";
import { CollectionsToolbar } from "./CollectionsToolbar";
import { useCollectionsFleet } from "./state/useCollectionsFleet";
import { ImportPanel } from "./transfer/ImportPanel";

interface CollectionsPageProps {
  onNavigate: Navigate;
}

export function CollectionsPage({ onNavigate }: CollectionsPageProps) {
  const [showImport, setShowImport] = useState(false);
  const {
    collections, loadError, load, visibleEntries, totalCount,
    searchQuery, setSearchQuery, sortKey, setSortKey, healthFilter, setHealthFilter,
  } = useCollectionsFleet();

  return (
    <div className="df-rise" style={{ padding: `${theme.space.xl}px`, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        title="Collections"
        subtitle={collections ? `${totalCount} collection${totalCount === 1 ? "" : "s"} — each with its own schema, ingestion and search pipeline` : " "}
        actions={
          <>
            <Button variant="secondary" onClick={() => setShowImport((v) => !v)}>
              {showImport ? "Cancel import" : "Import collection"}
            </Button>
            <Button variant="primary" onClick={() => onNavigate({ name: "new-collection" })}>
              + New collection
            </Button>
          </>
        }
      />
      {showImport && (
        <div className="df-rise" style={{ marginBottom: theme.space.l }}>
          <ImportPanel onNavigate={onNavigate} />
        </div>
      )}
      {loadError && <ErrorState message={loadError} onRetry={load} />}
      {!loadError && !collections && <LoadingState label="loading collections…" />}
      {!loadError && collections && collections.length === 0 && (
        <EmptyState
          title="No collections yet"
          subtitle="A collection pairs a metadata schema with its own ingestion and search pipeline — create the first one to start ingesting documents."
          action={<Button variant="primary" onClick={() => onNavigate({ name: "new-collection" })}>Create the first one</Button>}
        />
      )}
      {collections && collections.length > 0 && (
        <>
          <CollectionsToolbar
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            healthFilter={healthFilter}
            onHealthFilterChange={setHealthFilter}
            sortKey={sortKey}
            onSortKeyChange={setSortKey}
            visibleCount={visibleEntries.length}
            totalCount={totalCount}
          />
          {visibleEntries.length === 0 ? (
            <EmptyState
              title="No collections match"
              subtitle="Try a different name, or clear the health filter."
              action={<Button variant="secondary" onClick={() => { setSearchQuery(""); setHealthFilter("all"); }}>Clear filters</Button>}
            />
          ) : (
            <div className="df-stagger" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: theme.space.l }}>
              {visibleEntries.map(({ collection, health, healthError, docCount, jobRunning }) => (
                <CollectionCard
                  key={collection.id}
                  collection={collection}
                  health={health}
                  healthError={healthError}
                  docCount={docCount}
                  jobRunning={jobRunning}
                  onClick={() => onNavigate({ name: "collection", collectionId: collection.id })}
                  onDeleted={load}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
