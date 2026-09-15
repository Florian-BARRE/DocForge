// ====== Code Summary ======
// The composition root: owns the current View and dispatches to the one matching page. Hand-
// rolled routing (no router dependency) — a plain useState<View> is enough for this app's depth.

import { lazy, Suspense, useCallback, useState } from "react";
import { KeyDetailPage } from "./features/auth/KeyDetailPage";
import { SettingsPage } from "./features/auth/SettingsPage";
import { CollectionDetailPage } from "./features/collections/CollectionDetailPage";
import { CollectionOverview } from "./features/collections/CollectionOverview";
import { CollectionSearchPage } from "./features/collections/CollectionSearchPage";
import { CollectionShell } from "./features/collections/CollectionShell";
import { CollectionsPage } from "./features/collections/CollectionsPage";
import { ImportCollectionPage } from "./features/collections/ImportCollectionPage";
import { CollectionSettingsPage } from "./features/collections/settings/CollectionSettingsPage";
import { CollectionWizard } from "./features/collections/wizard/CollectionWizard";
import { HomePage } from "./features/home/HomePage";
import { ActivityPage } from "./features/jobs/ActivityPage";
import { JobDetailPage } from "./features/monitoring/JobDetailPage";
import { CollectionActivityTab } from "./features/jobs/CollectionActivityTab";
import { WorkersPanel } from "./features/monitoring/WorkersPanel";
import { SearchLabPage } from "./features/search/SearchLabPage";
import { ErrorBoundary } from "./shell/ErrorBoundary";
import { LoadingState } from "./components/LoadingState";
import { CommandPalette } from "./shell/command-palette/CommandPalette";
import { useCommandPaletteHotkey } from "./shell/command-palette/useCommandPaletteHotkey";
import { Sidebar, SIDEBAR_EXPANDED_WIDTH, SIDEBAR_RAIL_WIDTH } from "./shell/sidebar/Sidebar";
import { useSidebarExpanded } from "./shell/sidebar/useSidebarExpanded";
import { ToastProvider } from "./shell/toast";
import { theme } from "./theme";
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
  // Owned here (not inside Sidebar) because the spacer below needs the SAME expansion state Sidebar
  // renders with, to size its initial width before Sidebar's own effect reports in.
  const { expanded, toggleExpanded } = useSidebarExpanded();
  // Mirrors Sidebar's actual REFLOW state (expanded on a wide viewport only — a compact viewport
  // overlays instead) via `onExpandedChange`, so the spacer below always reserves the full width and
  // content is pushed, never partially covered. (A `position: fixed` rail that's wider than this
  // spacer used to clip a sliver of content at rest — the iteration-2 sidebar-overlap regression.)
  const [sidebarWidth, setSidebarWidth] = useState(() => (expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH));
  const onSidebarExpandedChange = useCallback((expanded: boolean) => {
    setSidebarWidth(expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH);
  }, []);

  // The ⌘K command palette is a root-level overlay, not a routed view — it must stay reachable
  // (and its state untouched) no matter which page `view` currently points at.
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  useCommandPaletteHotkey(openPalette);

  return (
    <ToastProvider>
    <div style={{ height: "100%", display: "flex" }}>
      <Sidebar
        view={view}
        onNavigate={setView}
        expanded={expanded}
        onToggleExpanded={toggleExpanded}
        onExpandedChange={onSidebarExpandedChange}
        onOpenPalette={openPalette}
      />
      <CommandPalette open={paletteOpen} view={view} onNavigate={setView} onClose={closePalette} />
      {/* Reserves the rail's current width in normal flow — always in lockstep with the `<nav>`'s
          own rendered width (see onSidebarExpandedChange above), so content is pushed by the FULL
          width whenever the sidebar expands, never left partially underneath it. */}
      <div style={{
        width: sidebarWidth, flexShrink: 0,
        transition: "width .16s cubic-bezier(0.22, 1, 0.36, 1)",
      }} />
      {/* A horizontal gutter so page content clears the rail's right border with breathing room
          (pages add their own inner padding on top) instead of sitting flush against the sidebar —
          fixes the "sidebar and content too tight" report. Horizontal only, so height:100% pages
          (CollectionShell) keep their full vertical box. */}
      <div style={{ flex: 1, minWidth: 0, minHeight: 0, padding: `0 ${theme.space.l}px` }}>
      {/* Keyed by view.name so navigating away (shell nav, or the fallback's own action) always
          remounts a fresh boundary — a crashed view never keeps blocking an unrelated route. */}
      <ErrorBoundary key={view.name} onReset={() => setView({ name: "overview" })}>
        {view.name === "overview" && <HomePage onNavigate={setView} />}
        {view.name === "collections" && <CollectionsPage onNavigate={setView} initialHealthFilter={view.health} />}
        {view.name === "new-collection" && <CollectionWizard onNavigate={setView} />}
        {view.name === "import-collection" && <ImportCollectionPage onNavigate={setView} />}
        {view.name === "collection" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <CollectionOverview collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-schema" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <CollectionDetailPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-settings" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <CollectionSettingsPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-pipelines" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView} pipelineStage={view.stage ?? "ingestion"}>
            {view.stage === "search" ? (
              <CollectionSearchPage collectionId={view.collectionId} onNavigate={setView} />
            ) : (
              <Suspense fallback={<LoadingState label="loading pipeline editor…" />}>
                <CollectionPipelinePage collectionId={view.collectionId} onNavigate={setView} />
              </Suspense>
            )}
          </CollectionShell>
        )}
        {view.name === "collection-activity" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <CollectionActivityTab collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-documents" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <Suspense fallback={<LoadingState label="loading documents…" />}>
              <CorpusPage collectionId={view.collectionId} onNavigate={setView} />
            </Suspense>
          </CollectionShell>
        )}
        {view.name === "collection-search" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <SearchLabPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "document" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <Suspense fallback={<LoadingState label="loading document…" />}>
              <DocumentPage collectionId={view.collectionId} documentId={view.documentId} onNavigate={setView} />
            </Suspense>
          </CollectionShell>
        )}
        {view.name === "job" && (
          <CollectionShell collectionId={view.collectionId} onNavigate={setView}>
            <JobDetailPage jobId={view.jobId} collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "activity" && <ActivityPage tab={view.tab ?? "jobs"} onNavigate={setView} />}
        {view.name === "fleet" && <WorkersPanel onNavigate={setView} />}
        {view.name === "settings" && <SettingsPage section={view.section ?? "keys"} onNavigate={setView} />}
        {view.name === "api-key" && <KeyDetailPage keyId={view.keyId} onNavigate={setView} />}
      </ErrorBoundary>
      </div>
    </div>
    </ToastProvider>
  );
}
