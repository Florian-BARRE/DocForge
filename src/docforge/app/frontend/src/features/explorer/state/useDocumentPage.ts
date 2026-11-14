// ====== Code Summary ======
// State behind a single document's explorer: the document's own identity load (with retry), the
// active tab + the block the Chunks tab asks the IR tab to focus, the per-tab lazy fetches
// (useDocumentTabs), the breadcrumb trail contributed to the collection shell, and the callbacks that
// patch the loaded document. Extracted from `DocumentPage` so that component only renders.

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FieldSpec } from "../../../api/collections";
import { getDocument, type DocumentDetail } from "../../../api/explorer";
import type { BreadcrumbItem } from "../../../components/Breadcrumb";
import { useCollectionBreadcrumbExtra } from "../../../shell/collectionBreadcrumbExtra";
import { documentDisplayName } from "../format";
import { mergeSavedMetadata, type DraftValues } from "../metadata/edit/metadataDraft";
import { useDocumentTabs, type DocumentTabKey } from "./useDocumentTabs";

export function useDocumentPage(collectionId: string, documentId: string) {
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

  // Grows the enclosing CollectionShell's own "Collections / {collection}" breadcrumb into this
  // page's full trail (see useCollectionBreadcrumbExtra) — memoized so the context effect below
  // doesn't refire every render. Contributed only once the filename is known; cleared (via the
  // hook's own cleanup) on unmount or while `document` is still loading.
  const breadcrumbExtra = useMemo<BreadcrumbItem[]>(() => [
    { label: "Documents", view: { name: "collection-documents", collectionId } },
    { label: document ? documentDisplayName(document) : "" },
  ], [collectionId, document]);
  useCollectionBreadcrumbExtra(document ? breadcrumbExtra : null);

  const jumpToBlock = (blockId: string) => {
    setFocusBlockId(blockId);
    setActiveTab("ir");
  };

  const handleDocumentEnabledChanged = (enabled: boolean) => {
    setDocument((prev) => (prev ? { ...prev, enabled } : prev));
  };

  const handleMetadataSaved = useCallback((updated: DraftValues, specs: FieldSpec[]) => {
    setDocument((prev) => (prev ? { ...prev, metadata: mergeSavedMetadata(prev.metadata, updated, specs) } : prev));
  }, []);

  return {
    document, error, load, activeTab, setActiveTab, focusBlockId, tabs,
    jumpToBlock, handleDocumentEnabledChanged, handleMetadataSaved,
  };
}
