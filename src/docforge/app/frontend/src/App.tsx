// ====== Code Summary ======
// The composition root: owns the current View and dispatches to the one matching page. Hand-
// rolled routing (no router dependency) — a plain useState<View> is enough for this app's depth.

import { useState } from "react";
import { AuthKeysPage } from "./features/auth/AuthKeysPage";
import { KeyDetailPage } from "./features/auth/KeyDetailPage";
import { CollectionDetailPage } from "./features/collections/CollectionDetailPage";
import { CollectionEditPage } from "./features/collections/CollectionEditPage";
import { CollectionOverview } from "./features/collections/CollectionOverview";
import { CollectionPipelinePage } from "./features/collections/CollectionPipelinePage";
import { CollectionSearchPage } from "./features/collections/CollectionSearchPage";
import { CollectionShell } from "./features/collections/CollectionShell";
import { CollectionsPage } from "./features/collections/CollectionsPage";
import { CollectionWizard } from "./features/collections/wizard/CollectionWizard";
import { DocumentPage } from "./features/explorer/DocumentPage";
import { DocumentsPage } from "./features/explorer/DocumentsPage";
import { JobDetailPage } from "./features/monitoring/JobDetailPage";
import { JobsPage } from "./features/monitoring/JobsPage";
import { WorkersPanel } from "./features/monitoring/WorkersPanel";
import { SearchLabPage } from "./features/search/SearchLabPage";
import { TopBar } from "./shell/TopBar";
import type { View } from "./shell/view";

export function App() {
  const [view, setView] = useState<View>({ name: "collections" });

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <TopBar view={view} onNavigate={setView} />
      <div style={{ flex: 1, minHeight: 0 }}>
        {view.name === "collections" && <CollectionsPage onNavigate={setView} />}
        {view.name === "new-collection" && <CollectionWizard onNavigate={setView} />}
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
            <CollectionPipelinePage collectionId={view.collectionId} onNavigate={setView} />
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
            <DocumentsPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "collection-search" && (
          <CollectionShell collectionId={view.collectionId} active="search" onNavigate={setView}>
            <SearchLabPage collectionId={view.collectionId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "document" && (
          <CollectionShell collectionId={view.collectionId} active="documents" onNavigate={setView}>
            <DocumentPage collectionId={view.collectionId} documentId={view.documentId} onNavigate={setView} />
          </CollectionShell>
        )}
        {view.name === "job" && <JobDetailPage jobId={view.jobId} collectionId={view.collectionId} onNavigate={setView} />}
        {view.name === "workers" && <WorkersPanel onNavigate={setView} />}
        {view.name === "api-keys" && <AuthKeysPage onNavigate={setView} />}
        {view.name === "api-key" && <KeyDetailPage keyId={view.keyId} onNavigate={setView} />}
      </div>
    </div>
  );
}
