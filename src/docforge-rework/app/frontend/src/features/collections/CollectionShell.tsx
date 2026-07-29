// ====== Code Summary ======
// The collection workspace chrome — a header (name + contract summary + upload/edit actions) and a
// TWO-LEVEL nav shared by every view nested under a collection. Level 1 groups the workspace into
// Corpus (the documents + how they're ingested) and Search (how the corpus is queried); level 2 is
// the contextual sub-tabs. A document's detail view is nested under Corpus›Documents, so the nav
// stays visible while inspecting a document. Fetches the collection only to render this chrome —
// each nested page still owns its own data fetch.

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
import { theme as t } from "../../theme";
import { UploadPanel } from "./UploadPanel";

// A sub-tab key — the caller passes the active one; the section (level-1 group) is derived from it.
export type CollectionTabKey =
  | "documents" | "pipeline" | "jobs" | "schema"   // Corpus
  | "search" | "search-pipeline";                  // Search

type Section = "corpus" | "search";

const SECTION_OF: Record<CollectionTabKey, Section> = {
  documents: "corpus", pipeline: "corpus", jobs: "corpus", schema: "corpus",
  search: "search", "search-pipeline": "search",
};

const SUBTABS: Record<Section, TabItem<CollectionTabKey>[]> = {
  corpus: [
    { key: "documents", label: "Documents" },
    { key: "pipeline", label: "Ingestion pipeline" },
    { key: "jobs", label: "Jobs" },
    { key: "schema", label: "Schema" },
  ],
  search: [
    { key: "search", label: "Search" },
    { key: "search-pipeline", label: "Search pipeline" },
  ],
};

// The landing sub-tab when a level-1 section is clicked.
const SECTION_DEFAULT: Record<Section, CollectionTabKey> = { corpus: "documents", search: "search" };

function viewForTab(tab: CollectionTabKey, collectionId: string): View {
  switch (tab) {
    case "documents": return { name: "collection-documents", collectionId };
    case "pipeline": return { name: "collection-pipeline", collectionId };
    case "jobs": return { name: "collection-jobs", collectionId };
    case "schema": return { name: "collection", collectionId };
    case "search": return { name: "collection-search", collectionId };
    case "search-pipeline": return { name: "collection-search-pipeline", collectionId };
  }
}

interface CollectionShellProps {
  collectionId: string;
  active: CollectionTabKey;
  onNavigate: Navigate;
  children: ReactNode;
}

function SectionTab({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? t.color.accentSoft : "transparent",
        color: active ? t.color.accent : t.color.dim,
        border: `1px solid ${active ? t.color.accentLine : "transparent"}`,
        borderRadius: t.radius.m, padding: "7px 16px",
        fontSize: t.font.size.l, fontWeight: active ? 700 : 600, cursor: "pointer",
        transition: "background .16s ease, color .16s ease, border-color .16s ease",
      }}
    >
      {label}
    </button>
  );
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

  const section = SECTION_OF[active];
  const maxSizeMb = (collection.max_file_size_bytes / (1024 * 1024)).toFixed(1);
  const subtitle = `${collection.supported_formats.join(", ")} · ${maxSizeMb} MB max · `
    + `${collection.fields.length} field${collection.fields.length === 1 ? "" : "s"}`;

  return (
    <div className="df-rise" style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: `${t.space.xl}px ${t.space.xl}px 0`, maxWidth: 1200, margin: "0 auto", width: "100%" }}>
        <PageHeader
          eyebrow={<BackLink label="Collections" onClick={() => onNavigate({ name: "collections" })} />}
          title={
            <span style={{ display: "inline-flex", alignItems: "center", gap: t.space.s }}>
              {collection.name}
              {collection.needs_reindex && <Chip tone="warn">needs reindex</Chip>}
            </span>
          }
          subtitle={subtitle}
          actions={
            <>
              <Button variant="secondary" onClick={() => onNavigate({ name: "collection-edit", collectionId })}>Edit</Button>
              <Button variant="primary" onClick={() => setShowUpload((v) => !v)}>{showUpload ? "Cancel upload" : "Upload"}</Button>
            </>
          }
        />
        {showUpload && (
          <div style={{ marginBottom: t.space.l, maxWidth: 480 }}>
            <UploadPanel
              collectionId={collectionId}
              fields={collection.fields}
              onUploaded={(jobId) => { setShowUpload(false); onNavigate({ name: "job", collectionId, jobId }); }}
            />
          </div>
        )}

        {/* Level 1 — Corpus | Search. */}
        <div style={{ display: "flex", gap: t.space.xs, marginBottom: t.space.m }}>
          <SectionTab active={section === "corpus"} label="Corpus"
            onClick={() => onNavigate(viewForTab(SECTION_DEFAULT.corpus, collectionId))} />
          <SectionTab active={section === "search"} label="Search"
            onClick={() => onNavigate(viewForTab(SECTION_DEFAULT.search, collectionId))} />
        </div>
        {/* Level 2 — the active section's sub-tabs. */}
        <TabNav tabs={SUBTABS[section]} active={active} onSelect={(tab) => onNavigate(viewForTab(tab, collectionId))} />
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </div>
  );
}
