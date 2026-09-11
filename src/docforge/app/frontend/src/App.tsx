// ====== Code Summary ======
// The composition root: owns the current View and dispatches to the one matching page. Hand-
// rolled routing (no router dependency) — a plain useState<View> is enough for this app's depth.

import { lazy, Suspense, useCallback, useState } from "react";
import { AuthKeysPage } from "./features/auth/AuthKeysPage";
import { KeyDetailPage } from "./features/auth/KeyDetailPage";
import { CollectionDetailPage } from "./features/collections/CollectionDetailPage";
import { CollectionEditPage } from "./features/collections/CollectionEditPage";
import { CollectionOverview } from "./features/collections/CollectionOverview";
import { CollectionSearchPage } from "./features/collections/CollectionSearchPage";
import { CollectionShell } from "./features/collections/CollectionShell";
import { CollectionsPage } from "./features/collections/CollectionsPage";
import { ImportCollectionPage } from "./features/collections/ImportCollectionPage";
import { CollectionWizard } from "./features/collections/wizard/CollectionWizard";
import { HomePage } from "./features/home/HomePage";
import { AllJobsPage } from "./features/jobs/AllJobsPage";
import { JobDetailPage } from "./features/monitoring/JobDetailPage";
import { JobsPage } from "./features/monitoring/JobsPage";
import { WorkersPanel } from "./features/monitoring/WorkersPanel";
import { SearchLabPage } from "./features/search/SearchLabPage";
import { ErrorBoundary } from "./shell/ErrorBoundary";
import { LoadingState } from "./components/LoadingState";
import { Sidebar, SIDEBAR_EXPANDED_WIDTH, SIDEBAR_RAIL_WIDTH } from "./shell/sidebar/Sidebar";
import { useSidebarPin } from "./shell/sidebar/useSidebarPin";
import { ToastProvider } from "./shell/toast";
import { parseViewFromHash } from "./shell/urlSync";
import { useUrlSync } from "./shell/useUrlSync";
import type { View } from "./shell/view";

// Lazy-loaded routes: each pulls in a heavy, rarely-co-used feature (TanStack table/virtual for
// the corpus grid, the whole stage-rail canvas for the pipeline editor, the Sankey provenance
// graph for the document explorer) — deferring them keeps the initial bundle to app shell + the
// features most users hit first.
const CorpusPage = lazy(() => import("./features/corpus/CorpusPage").then((m) => ({ default: m.CorpusPage })));
const CollectionPipelinePage = lazy(() =>
  import("./features/collections/CollectionPipelinePage").then((m) => ({ default: m.CollectionPipelinePage })),
);
const DocumentPage = lazy(() => import("./features/explorer/DocumentPage").then((m) => ({ default: m.DocumentPage })));

export function App() {
  // Bootstrap from the current URL hash so a refresh or a shared link restores the same view.
  const [view, setView] = useState<View>(() => parseViewFromHash(window.location.hash));
  useUrlSync(view, setView);
  // Owned here (not inside Sidebar) because the spacer below needs the SAME pin state Sidebar
  // renders with, to size its initial width before Sidebar's own effect reports in.
  const { pinned, togglePinned } = useSidebarPin();
  // Mirrors Sidebar's actual rendered width for ANY reason it expanded — hover, focus, or pin —
  // via `onExpandedChange`, so the spacer below always reserves the full width and content is
  // pushed, never partially covered. (A `position: fixed` rail that's wider than this spacer used
  // to clip a sliver of content at rest — the iteration-2 sidebar-overlap regression.)
  const [sidebarWidth, setSidebarWidth] = useState(() => (pinned ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH));
  const onSidebarExpandedChange = useCallback((expanded: boolean) => {
    setSidebarWidth(expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH);
  }, []);

  return (
    <ToastProvider>
    <div style={{ height: "100%", display: "flex" }}>
      <Sidebar
        view={view}
        onNavigate={setView}
        pinned={pinned}
        onTogglePin={togglePinned}
        onExpandedChange={onSidebarExpandedChange}
      />
      {/* Reserves the rail's current width in normal flow — always in lockstep with the `<nav>`'s
          own rendered width (see onSidebarExpandedChange above), so content is pushed by the FULL
          width whenever the sidebar expands, never left partially underneath it. */}
      <div style={{
        width: sidebarWidth, flexShrink: 0,
        transition: "width .16s cubic-bezier(0.22, 1, 0.36, 1)",
      }} />
      <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>
      {/* Keyed by view.name so navigating away (shell nav, or the fallback's own action) always
          remounts a fresh boundary — a crashed view never keeps blocking an unrelated route. */}
      <ErrorBoundary key={view.name} onReset={() => setView({ name: "home" })}>
        {view.name === "home" && <HomePage onNavigate={setView} />}
        {view.name === "collections" && <CollectionsPage onNavigate={setView} initialHealthFilter={view.health} />}
        {view.name === "new-collection" && <CollectionWizard onNavigate={setView} />}
        {view.name === "import-collection" && <ImportCollectionPage onNavigate={setView} />}
        {view.name === "collection" && (
          <CollectionShell collectionId={view.collectionId} active="overview" onNavigate={setView}>
            <CollectionOverview collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-metadata" && (
          <CollectionShell collectionId={view.collectionId} active="metadata" onNavigate={setView}>
            <CollectionDetailPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-edit" && <CollectionEditPage collectionId={view.collectionId} onNavigate={setView} />}
        {view.name === "collection-pipeline" && (
          <CollectionShell collectionId={view.collectionId} active="pipeline" onNavigate={setView}>
            <Suspense fallback={<LoadingState label="loading pipeline editor…" />}>
              <CollectionPipelinePage collectionId={view.collectionId} onNavigate={setView} />
            </Suspense>
          </CollectionShell>
        )}
        {view.name === "collection-search-pipeline" && (
          <CollectionShell collectionId={view.collectionId} active="search-pipeline" onNavigate={setView}>
            <CollectionSearchPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-jobs" && (
          <CollectionShell collectionId={view.collectionId} active="jobs" onNavigate={setView}>
            <JobsPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-documents" && (
          <CollectionShell collectionId={view.collectionId} active="documents" onNavigate={setView}>
            <Suspense fallback={<LoadingState label="loading corpus…" />}>
              <CorpusPage collectionId={view.collectionId} onNavigate={setView} />
            </Suspense>
          </CollectionShell>
        )}
        {view.name === "collection-search" && (
          <CollectionShell collectionId={view.collectionId} active="search" onNavigate={setView}>
            <SearchLabPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "document" && (
          <CollectionShell collectionId={view.collectionId} active="documents" onNavigate={setView}>
            <Suspense fallback={<LoadingState label="loading document…" />}>
              <DocumentPage collectionId={view.collectionId} documentId={view.documentId} onNavigate={setView} />
            </Suspense>
          </CollectionShell>
        )}
        {view.name === "job" && <JobDetailPage jobId={view.jobId} collectionId={view.collectionId} onNavigate={setView} />}
        {view.name === "all-jobs" && <AllJobsPage onNavigate={setView} />}
        {view.name === "workers" && <WorkersPanel onNavigate={setView} />}
        {view.name === "api-keys" && <AuthKeysPage onNavigate={setView} />}
        {view.name === "api-key" && <KeyDetailPage keyId={view.keyId} onNavigate={setView} />}
      </ErrorBoundary>
      </div>
    </div>
    </ToastProvider>
  );
}
