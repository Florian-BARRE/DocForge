// ====== Code Summary ======
// The landing page: every collection as a card, "New collection" to open the wizard, click a
// card to open its detail page.

import { useEffect, useState } from "react";
import { listCollections, type Collection } from "../../api/collections";
import { Button } from "../../components/Button";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
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

  const count = collections?.length ?? 0;
  return (
    <div className="df-rise" style={{ padding: `${theme.space.xl}px`, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        title="Collections"
        subtitle={collections ? `${count} contract${count === 1 ? "" : "s"} — each a schema + ingestion + search pipeline` : " "}
        actions={
          <Button variant="primary" onClick={() => onNavigate({ name: "new-collection" })}>
            + New collection
          </Button>
        }
      />
      {error && <ErrorState message={error} onRetry={load} />}
      {!error && !collections && <LoadingState label="loading collections…" />}
      {!error && collections && collections.length === 0 && (
        <div
          style={{
            border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
            padding: `${theme.space.xxl}px`, textAlign: "center", color: theme.color.dim,
          }}
        >
          <div style={{ fontSize: theme.font.size.l, marginBottom: theme.space.s }}>No collections yet.</div>
          <Button variant="primary" onClick={() => onNavigate({ name: "new-collection" })}>Create the first one</Button>
        </div>
      )}
      {collections && collections.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: theme.space.l }}>
          {collections.map((c) => (
            <CollectionCard key={c.id} collection={c} onClick={() => onNavigate({ name: "collection-documents", collectionId: c.id })} />
          ))}
        </div>
      )}
    </div>
  );
}
