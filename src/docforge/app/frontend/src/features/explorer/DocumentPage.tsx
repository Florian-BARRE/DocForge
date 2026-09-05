// ====== Code Summary ======
// A single document's explorer: header (filename, status, facts) plus four tabs — Overview,
// Pages, IR and Chunks. Per-tab fetch/cache lives in `useDocumentTabs`; the header's action
// cluster (toggle/re-ingest/delete) lives in `DocumentPageActions` — this component owns just the
// document's own identity load + tab switching.

import { useEffect, useState } from "react";
import { getDocument, type DocumentDetail } from "../../api/explorer";
import { BackLink } from "../../components/BackLink";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageBoxLightbox } from "../../components/PageBoxLightbox";
import { PageHeader } from "../../components/PageHeader";
import { TabNav, tabButtonId } from "../../components/TabNav";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { ChunksTab } from "./chunks/ChunksTab";
import { DocumentPageActions } from "./DocumentPageActions";
import { DocumentStatusChip } from "./DocumentStatusChip";
import { formatBytes, formatDateTime } from "./format";
import { IRTab } from "./ir/IRTab";
import { LayoutTab } from "./layout/LayoutTab";
import { OverviewTab } from "./overview/OverviewTab";
import { PagesTab } from "./pages/PagesTab";
import { useDocumentTabs, type DocumentTabKey } from "./state/useDocumentTabs";

// "Overview" collides with the collection shell's own top-level "Overview" tab — a document is
// nested two levels under that, so its landing tab reads "Summary" instead (still the same
// facts+metadata content; see OverviewTab.tsx).
const TABS: { key: DocumentTabKey; label: string }[] = [
  { key: "overview", label: "Summary" },
  { key: "pages", label: "Pages" },
  { key: "layout", label: "Layout" },
  { key: "ir", label: "IR" },
  { key: "chunks", label: "Chunks" },
];

interface DocumentPageProps {
  collectionId: string;
  documentId: string;
  onNavigate: Navigate;
}

export function DocumentPage({ collectionId, documentId, onNavigate }: DocumentPageProps) {
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<DocumentTabKey>("overview");
  const [focusBlockId, setFocusBlockId] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getDocument(documentId)
      .then(setDocument)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };
  useEffect(load, [documentId]);

  const tabs = useDocumentTabs(documentId, activeTab);

  const jumpToBlock = (blockId: string) => {
    setFocusBlockId(blockId);
    setActiveTab("ir");
  };

  const handleDocumentEnabledChanged = (enabled: boolean) => {
    setDocument((prev) => (prev ? { ...prev, enabled } : prev));
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!document) return <LoadingState label="loading document…" />;

  return (
    <div className="df-rise" style={{ padding: `${theme.space.m}px ${theme.space.xl}px ${theme.space.xl}px`, overflowY: "auto", height: "100%", display: "flex", flexDirection: "column", maxWidth: activeTab === "layout" ? 1560 : 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        compact
        eyebrow={<BackLink label="Documents" onClick={() => onNavigate({ name: "collection-documents", collectionId })} />}
        title={<span style={{ wordBreak: "break-word" }}>{document.filename}</span>}
        subtitle={
          <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            <span>
              {document.format.toUpperCase()} · {document.page_count ?? "—"} page(s) · {formatBytes(document.file_size)} · created {formatDateTime(document.created_at)}
            </span>
            <DocumentStatusChip status={document.status} />
            {!document.enabled && <Chip tone="warn">disabled</Chip>}
          </span>
        }
        actions={
          <DocumentPageActions
            documentId={documentId}
            collectionId={collectionId}
            enabled={document.enabled}
            onEnabledChanged={handleDocumentEnabledChanged}
            onNavigate={onNavigate}
          />
        }
      />

      <TabNav
        tabs={TABS}
        active={activeTab}
        onSelect={setActiveTab}
        navId="document-tabs"
        ariaLabel="Document sections"
        panelId="document-tabpanel"
      />

      {/* Keyed on the active tab so switching replays a short df-rise instead of hard-cutting. */}
      <div
        key={activeTab}
        className="df-rise"
        role="tabpanel"
        id="document-tabpanel"
        aria-labelledby={tabButtonId("document-tabs", activeTab)}
        style={{ marginTop: theme.space.m, flex: 1, minHeight: 0 }}
      >
        {activeTab === "overview" && <OverviewTab document={document} />}
        {activeTab === "pages" &&
          (tabs.pagesError ? (
            <ErrorState message={tabs.pagesError} onRetry={tabs.loadPages} />
          ) : tabs.pages ? (
            <PagesTab pages={tabs.pages} />
          ) : (
            <LoadingState label="loading pages…" />
          ))}
        {activeTab === "layout" && (
          <LayoutTab
            ir={tabs.ir}
            pages={tabs.pages}
            chunks={tabs.chunks}
            provenance={tabs.provenance}
            // Only IR/pages are load-bearing for the page↔block view — a chunks fetch failure
            // degrades to a non-blocking notice (chunk grouping/provenance unavailable) rather
            // than blanking the whole tab, per the tab's own degrade-without-chunks design.
            error={tabs.irError ?? tabs.pagesError}
            chunksError={tabs.chunksError}
            onRetry={() => {
              tabs.loadIr();
              tabs.loadPages();
              tabs.loadProvenance();
            }}
            onRetryChunks={tabs.loadChunks}
          />
        )}
        {activeTab === "ir" &&
          (tabs.irError ? (
            <ErrorState message={tabs.irError} onRetry={tabs.loadIr} />
          ) : tabs.ir ? (
            <IRTab ir={tabs.ir} focusBlockId={focusBlockId} />
          ) : (
            <LoadingState label="loading IR…" />
          ))}
        {activeTab === "chunks" &&
          (tabs.chunksError ? (
            <ErrorState message={tabs.chunksError} onRetry={tabs.loadChunks} />
          ) : tabs.chunks ? (
            <ChunksTab
              chunks={tabs.chunks}
              onJumpToBlock={jumpToBlock}
              onChunkEnabledChanged={tabs.handleChunkEnabledChanged}
              onShowChunkOnPage={tabs.chunkLocator}
            />
          ) : (
            <LoadingState label="loading chunks…" />
          ))}
      </div>

      {tabs.boxLightbox && (
        <PageBoxLightbox
          renderBlobHash={tabs.boxLightbox.renderBlobHash}
          width={tabs.boxLightbox.width}
          height={tabs.boxLightbox.height}
          boxes={tabs.boxLightbox.boxes}
          caption={tabs.boxLightbox.caption}
          onClose={tabs.closeBoxLightbox}
        />
      )}
    </div>
  );
}
