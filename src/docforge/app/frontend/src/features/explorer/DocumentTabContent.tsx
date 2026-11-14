// ====== Code Summary ======
// The body of the document page's active tab: overview / pages / layout / IR / chunks / trace. Each
// lazily fetched tab shows its own loading and error state; the fetches themselves live in
// `useDocumentTabs`, this component only picks what to render.

import type { DocumentDetail } from "../../api/explorer";
import type { DraftValues } from "./metadata/edit/metadataDraft";
import type { FieldSpec } from "../../api/collections";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { ChunksTab } from "./chunks/ChunksTab";
import { IRTab } from "./ir/IRTab";
import { LayoutTab } from "./layout/LayoutTab";
import { OverviewTab } from "./overview/OverviewTab";
import { PagesTab } from "./pages/PagesTab";
import type { DocumentTabKey, useDocumentTabs } from "./state/useDocumentTabs";
import { TraceTab } from "./trace/TraceTab";

interface DocumentTabContentProps {
  activeTab: DocumentTabKey;
  document: DocumentDetail;
  documentId: string;
  collectionId: string;
  tabs: ReturnType<typeof useDocumentTabs>;
  focusBlockId: string | null;
  onNavigate: Navigate;
  onJumpToBlock: (blockId: string) => void;
  onMetadataSaved: (updated: DraftValues, specs: FieldSpec[]) => void;
}

export function DocumentTabContent({
  activeTab, document, documentId, collectionId, tabs, focusBlockId, onNavigate, onJumpToBlock, onMetadataSaved,
}: DocumentTabContentProps) {
  return (
    <>
      {activeTab === "overview" && (
        <OverviewTab document={document} pages={tabs.pages} collectionId={collectionId} onNavigate={onNavigate} onMetadataSaved={onMetadataSaved} />
      )}
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
            onJumpToBlock={onJumpToBlock}
            onChunkEnabledChanged={tabs.handleChunkEnabledChanged}
            onShowChunkOnPage={tabs.chunkLocator}
          />
        ) : (
          <LoadingState label="loading chunks…" />
        ))}
      {activeTab === "trace" && (
        <TraceTab
          documentId={documentId}
          provenance={tabs.provenance}
          error={tabs.provenanceError}
          onRetry={tabs.loadProvenance}
        />
      )}
    </>
  );
}
