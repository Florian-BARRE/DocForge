// ====== Code Summary ======
// The typed route table: ONE entry per `View` variant, each a renderer that receives its own
// variant (so its params are typed — `view.documentId` only exists on "document") and the shell's
// `navigate`, and returns the page (wrapped in `CollectionShell` for the collection-scoped views).
// `ROUTES` is a mapped type over `View["name"]`, so adding a View variant without a route — or a
// route for a name that is not a View — is a compile error. The routed entry pages receive the
// shell's navigate as `onNavigate` (the boundary the routing characterization test pins); every
// component below them reaches it through `useNavigate()` instead of prop-drilling.
// It lives at the src root, not in shell/: it imports every feature page, and shell/ never
// imports a feature (layering guard).

// ====== Third-Party Library Imports ======
import { lazy, Suspense, type ReactNode } from "react";

// ====== Internal Project Imports ======
import { LoadingState } from "./components/LoadingState";
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
import { CollectionActivityTab } from "./features/jobs/CollectionActivityTab";
import { JobDetailPage } from "./features/jobs/JobDetailPage";
import { WorkersPanel } from "./features/jobs/WorkersPanel";
import { SearchLabPage } from "./features/search/SearchLabPage";
import type { Navigate, View } from "./shell/view";

// Lazy-loaded routes: each pulls in a heavy, rarely-co-used feature (TanStack table/virtual for
// the corpus grid, the whole stage-rail canvas for the pipeline editor, the Sankey provenance
// graph for the document explorer) — deferring them keeps the initial bundle to app shell + the
// features most users hit first.
const CorpusPage = lazy(() => import("./features/corpus/CorpusPage").then((m) => ({ default: m.CorpusPage })));
const CollectionPipelinePage = lazy(() =>
  import("./features/collections/CollectionPipelinePage").then((m) => ({ default: m.CollectionPipelinePage })),
);
const DocumentPage = lazy(() => import("./features/explorer/DocumentPage").then((m) => ({ default: m.DocumentPage })));

/** The names of the View variants. */
export type ViewName = View["name"];

/** The View variant with this name, params included. */
export type ViewOf<N extends ViewName> = Extract<View, { name: N }>;

/** Renders the page of one View variant. */
export type RouteRenderer<N extends ViewName> = (view: ViewOf<N>, navigate: Navigate) => ReactNode;

/** One renderer per View variant — exhaustive by construction. */
export type RouteTable = { [N in ViewName]: RouteRenderer<N> };

/** Wrap a collection-scoped page in its `CollectionShell` chrome (tabs, breadcrumb, header). */
function inCollectionShell(
  collectionId: string,
  navigate: Navigate,
  page: ReactNode,
  shellProps: { pipelineStage?: "ingestion" | "search"; settingsSection?: NonNullable<ViewOf<"collection-settings">["section"]> } = {},
): ReactNode {
  return (
    <CollectionShell collectionId={collectionId} onNavigate={navigate} {...shellProps}>
      {page}
    </CollectionShell>
  );
}

export const ROUTES: RouteTable = {
  overview: (_view, navigate) => <HomePage onNavigate={navigate} />,
  collections: (view, navigate) => <CollectionsPage onNavigate={navigate} initialHealthFilter={view.health} />,
  "new-collection": (_view, navigate) => <CollectionWizard onNavigate={navigate} />,
  "import-collection": (_view, navigate) => <ImportCollectionPage onNavigate={navigate} />,
  collection: (view, navigate) =>
    inCollectionShell(view.collectionId, navigate, <CollectionOverview collectionId={view.collectionId} onNavigate={navigate} />),
  "collection-schema": (view, navigate) =>
    inCollectionShell(view.collectionId, navigate, <CollectionDetailPage collectionId={view.collectionId} onNavigate={navigate} />),
  "collection-settings": (view, navigate) => {
    const section = view.section ?? "general";
    return inCollectionShell(
      view.collectionId,
      navigate,
      <CollectionSettingsPage collectionId={view.collectionId} section={section} onNavigate={navigate} />,
      { settingsSection: section },
    );
  },
  "collection-pipelines": (view, navigate) =>
    inCollectionShell(
      view.collectionId,
      navigate,
      view.stage === "search" ? (
        <CollectionSearchPage collectionId={view.collectionId} onNavigate={navigate} />
      ) : (
        <Suspense fallback={<LoadingState label="loading pipeline editor…" />}>
          <CollectionPipelinePage collectionId={view.collectionId} onNavigate={navigate} />
        </Suspense>
      ),
      { pipelineStage: view.stage ?? "ingestion" },
    ),
  "collection-activity": (view, navigate) =>
    inCollectionShell(view.collectionId, navigate, <CollectionActivityTab collectionId={view.collectionId} onNavigate={navigate} />),
  "collection-documents": (view, navigate) =>
    inCollectionShell(
      view.collectionId,
      navigate,
      <Suspense fallback={<LoadingState label="loading documents…" />}>
        <CorpusPage collectionId={view.collectionId} onNavigate={navigate} />
      </Suspense>,
    ),
  "collection-search": (view, navigate) =>
    inCollectionShell(view.collectionId, navigate, <SearchLabPage collectionId={view.collectionId} onNavigate={navigate} />),
  document: (view, navigate) =>
    inCollectionShell(
      view.collectionId,
      navigate,
      <Suspense fallback={<LoadingState label="loading document…" />}>
        <DocumentPage collectionId={view.collectionId} documentId={view.documentId} onNavigate={navigate} />
      </Suspense>,
    ),
  job: (view, navigate) =>
    inCollectionShell(view.collectionId, navigate, <JobDetailPage jobId={view.jobId} collectionId={view.collectionId} onNavigate={navigate} />),
  activity: (view, navigate) => <ActivityPage tab={view.tab ?? "jobs"} onNavigate={navigate} />,
  fleet: (_view, navigate) => <WorkersPanel onNavigate={navigate} />,
  settings: (view, navigate) => <SettingsPage section={view.section ?? "keys"} onNavigate={navigate} />,
  "api-key": (view, navigate) => <KeyDetailPage keyId={view.keyId} onNavigate={navigate} />,
};

/**
 * Render the page of `view`.
 *
 * @param view - The current view (the shell's state).
 * @param navigate - The shell's navigate function, handed to the routed entry page.
 * @returns The page element.
 */
export function renderRoute(view: View, navigate: Navigate): ReactNode {
  // One cast: TS cannot correlate `view.name` with its renderer through a union index, but the
  // RouteTable type already guarantees each renderer matches its own variant.
  return (ROUTES[view.name] as RouteRenderer<ViewName>)(view as never, navigate);
}
