// ====== Code Summary ======
// The collection workspace's persistent chrome — a header (name + contract summary + upload/edit
// actions) and a sub-nav tab strip, shared by every view nested under a collection (Overview,
// Documents, Search, Pipeline, Search pipeline, Jobs). Fetches the collection itself purely to
// render that chrome; each nested page still owns its own data fetch, so nothing here changes
// what a page does — only what wraps it. Upload lives here (not on the Overview page alone) so a
// document can be dropped in from any tab.

import { useEffect, useState, type ReactNode } from "react";
import { getCollection, type Collection } from "../../api/collections";
import { BackLink } from "../../components/BackLink";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { TabNav, type TabItem } from "../../components/TabNav";
import type { Navigate, View } from "../../shell/view";
import { theme } from "../../theme";
import { UploadPanel } from "./UploadPanel";

export type CollectionTabKey = "overview" | "documents" | "search" | "pipeline" | "search-pipeline" | "jobs";

const TABS: TabItem<CollectionTabKey>[] = [
  { key: "overview", label: "Overview" },
  { key: "documents", label: "Documents" },
  { key: "search", label: "Search" },
  { key: "pipeline", label: "Pipeline" },
  { key: "search-pipeline", label: "Search pipeline" },
  { key: "jobs", label: "Jobs" },
];

function viewForTab(tab: CollectionTabKey, collectionId: string): View {
  switch (tab) {
    case "overview": return { name: "collection", collectionId };
    case "documents": return { name: "collection-documents", collectionId };
    case "search": return { name: "collection-search", collectionId };
    case "pipeline": return { name: "collection-pipeline", collectionId };
    case "search-pipeline": return { name: "collection-search-pipeline", collectionId };
    case "jobs": return { name: "collection-jobs", collectionId };
  }
}

interface CollectionShellProps {
  collectionId: string;
  active: CollectionTabKey;
  onNavigate: Navigate;
  children: ReactNode;
}

export function CollectionShell({ collectionId, active, onNavigate, children }: CollectionShellProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);

  const load = () => {
    setError(null);
    getCollection(collectionId)
      .then(setCollection)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [collectionId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  const maxSizeMb = (collection.max_file_size_bytes / (1024 * 1024)).toFixed(1);
  const subtitle = `${collection.supported_formats.join(", ")} · ${maxSizeMb} MB max · `
    + `${collection.fields.length} field${collection.fields.length === 1 ? "" : "s"}`;

  return (
    <div className="df-rise" style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: `${theme.space.xl}px ${theme.space.xl}px 0`, maxWidth: 1200, margin: "0 auto", width: "100%" }}>
        <PageHeader
          eyebrow={<BackLink label="Collections" onClick={() => onNavigate({ name: "collections" })} />}
          title={
            <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.s }}>
              {collection.name}
              {collection.needs_reindex && <Chip tone="warn">needs reindex</Chip>}
            </span>
          }
          subtitle={subtitle}
          actions={
            <>
              <Button variant="secondary" onClick={() => onNavigate({ name: "collection-edit", collectionId })}>
                Edit
              </Button>
              <Button variant="primary" onClick={() => setShowUpload((v) => !v)}>
                {showUpload ? "Cancel upload" : "Upload"}
              </Button>
            </>
          }
        />
        {showUpload && (
          <div style={{ marginBottom: theme.space.l, maxWidth: 480 }}>
            <UploadPanel
              collectionId={collectionId}
              fields={collection.fields}
              onUploaded={(jobId) => {
                setShowUpload(false);
                onNavigate({ name: "job", collectionId, jobId });
              }}
            />
          </div>
        )}
        <TabNav tabs={TABS} active={active} onSelect={(tab) => onNavigate(viewForTab(tab, collectionId))} />
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </div>
  );
}
