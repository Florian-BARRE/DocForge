// ====== Code Summary ======
// The landing page: every collection as a card, "New collection" to open the wizard, click a
// card to open its detail page.

import { useEffect, useState } from "react";
import { listCollections, type Collection } from "../../api/collections";
import { Button } from "../../components/Button";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";
import type { Navigate } from "../../shell/view";
import { CollectionCard } from "./CollectionCard";

interface CollectionsPageProps {
  onNavigate: Navigate;
}

export function CollectionsPage({ onNavigate }: CollectionsPageProps) {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    listCollections()
      .then(setCollections)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, []);

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: theme.space.l }}>
        <h1 style={{ fontSize: theme.font.size.xl }}>Collections</h1>
        <div style={{ marginLeft: "auto" }}>
          <Button variant="primary" onClick={() => onNavigate({ name: "new-collection" })}>
            + New collection
          </Button>
        </div>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      {!error && !collections && <LoadingState label="loading collections…" />}
      {!error && collections && collections.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          No collections yet — create the first one.
        </div>
      )}
      {collections && collections.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: theme.space.m }}>
          {collections.map((c) => (
            <CollectionCard key={c.id} collection={c} onClick={() => onNavigate({ name: "collection", collectionId: c.id })} />
          ))}
        </div>
      )}
    </div>
  );
}
