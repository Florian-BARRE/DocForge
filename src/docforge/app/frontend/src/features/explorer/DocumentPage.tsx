// ====== Code Summary ======
// A single document's explorer: header (filename, status, facts) plus six tabs — Overview, Pages,
// Layout, IR, Chunks and Trace. The document's own identity load + tab switching live in
// `useDocumentPage` (per-tab fetch/cache in `useDocumentTabs`), the active tab's body in
// `DocumentTabContent`, and the header's action cluster (toggle/re-ingest/delete) in
// `DocumentPageActions` — this component only lays the page out.

import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageBoxLightbox } from "../../components/PageBoxLightbox";
import { PageHeader } from "../../components/PageHeader";
import { TabNav, tabButtonId } from "../../components/TabNav";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { DocumentPageActions } from "./DocumentPageActions";
import { DocumentStatusChip } from "./DocumentStatusChip";
import { DocumentTabContent } from "./DocumentTabContent";
import { documentDisplayName, formatBytes, formatDateTime } from "./format";
import { pageMaxWidthOf, TABS } from "./state/documentPageModel";
import { useDocumentPage } from "./state/useDocumentPage";

interface DocumentPageProps {
  collectionId: string;
  documentId: string;
  onNavigate: Navigate;
}

export function DocumentPage({ collectionId, documentId, onNavigate }: DocumentPageProps) {
  const {
    document, error, load, activeTab, setActiveTab, focusBlockId, tabs,
    jumpToBlock, handleDocumentEnabledChanged, handleMetadataSaved,
  } = useDocumentPage(collectionId, documentId);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!document) return <LoadingState label="loading document…" />;

  return (
    <div className="df-rise" style={{ padding: `${theme.space.m}px ${theme.space.xl}px ${theme.space.xl}px`, overflowY: "auto", height: "100%", display: "flex", flexDirection: "column", maxWidth: pageMaxWidthOf(activeTab), margin: "0 auto", width: "100%" }}>
      <PageHeader
        compact
        title={<span style={{ wordBreak: "break-word" }}>{documentDisplayName(document)}</span>}
        subtitle={
          <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            <span>
              {document.filename} · {document.format.toUpperCase()} · {document.page_count ?? "—"} page(s) · {formatBytes(document.file_size)} · created {formatDateTime(document.created_at)}
            </span>
            <DocumentStatusChip status={document.status} hasWarning={!!document.warning_reason} />
            {!document.enabled && <Chip tone="warn">disabled</Chip>}
            {document.warning_reason && (
              <Chip tone="warn" title={document.warning_reason}>
                {document.chunk_count === 0 ? "0 chunks" : "warning"}
              </Chip>
            )}
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
        <DocumentTabContent
          activeTab={activeTab}
          document={document}
          documentId={documentId}
          collectionId={collectionId}
          tabs={tabs}
          focusBlockId={focusBlockId}
          onNavigate={onNavigate}
          onJumpToBlock={jumpToBlock}
          onMetadataSaved={handleMetadataSaved}
        />
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
