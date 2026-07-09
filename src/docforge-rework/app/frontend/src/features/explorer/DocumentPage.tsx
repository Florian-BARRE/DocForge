// ====== Code Summary ======
// A single document's explorer: header (filename, status, facts) plus four tabs — Overview,
// Pages, IR and Chunks. Each tab's payload is fetched lazily on first activation and cached in
// this component's state for as long as the page stays mounted (navigating to a different
// document remounts the page, which is exactly when the cache should reset — see the app's
// "page remount = free refetch" convention).

import { useEffect, useState } from "react";
import {
  deleteDocument,
  getDocument,
  getDocumentChunks,
  getDocumentIR,
  getDocumentPages,
  type ChunkInfo,
  type DocumentDetail,
  type DocumentIR,
  type PageInfo,
} from "../../api/explorer";
import { BackLink } from "../../components/BackLink";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { TabNav } from "../../components/TabNav";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { ChunksTab } from "./chunks/ChunksTab";
import { DocumentEnabledToggle } from "./DocumentEnabledToggle";
import { DocumentStatusChip } from "./DocumentStatusChip";
import { formatBytes, formatDateTime } from "./format";
import { IRTab } from "./ir/IRTab";
import { OverviewTab } from "./overview/OverviewTab";
import { PagesTab } from "./pages/PagesTab";

type TabKey = "overview" | "pages" | "ir" | "chunks";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "pages", label: "Pages" },
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
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [focusBlockId, setFocusBlockId] = useState<string | null>(null);

  const [pages, setPages] = useState<PageInfo[] | null>(null);
  const [pagesError, setPagesError] = useState<string | null>(null);
  const [ir, setIr] = useState<DocumentIR | null>(null);
  const [irError, setIrError] = useState<string | null>(null);
  const [chunks, setChunks] = useState<ChunkInfo[] | null>(null);
  const [chunksError, setChunksError] = useState<string | null>(null);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    setError(null);
    getDocument(documentId)
      .then(setDocument)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [documentId]);

  const loadPages = () => {
    setPagesError(null);
    getDocumentPages(documentId).then(setPages).catch((e) => setPagesError(e instanceof Error ? e.message : String(e)));
  };
  const loadIr = () => {
    setIrError(null);
    getDocumentIR(documentId).then(setIr).catch((e) => setIrError(e instanceof Error ? e.message : String(e)));
  };
  const loadChunks = () => {
    setChunksError(null);
    getDocumentChunks(documentId).then(setChunks).catch((e) => setChunksError(e instanceof Error ? e.message : String(e)));
  };

  // Fetch each tab's payload once, the first time it is activated — never all four upfront.
  useEffect(() => {
    if (activeTab === "pages" && pages === null && !pagesError) loadPages();
    if (activeTab === "ir" && ir === null && !irError) loadIr();
    if (activeTab === "chunks" && chunks === null && !chunksError) loadChunks();
    // Deliberately reacting only to the tab/document — the load* functions themselves are stable
    // enough for this effect's purpose (avoid a re-run loop on every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, documentId]);

  const jumpToBlock = (blockId: string) => {
    setFocusBlockId(blockId);
    setActiveTab("ir");
  };

  const handleDocumentEnabledChanged = (enabled: boolean) => {
    setDocument((prev) => (prev ? { ...prev, enabled } : prev));
  };

  const handleChunkEnabledChanged = (chunkId: string, enabled: boolean) => {
    setChunks((prev) => (prev ? prev.map((chunk) => (chunk.id === chunkId ? { ...chunk, enabled } : chunk)) : prev));
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteDocument(documentId);
      onNavigate({ name: "collection-documents", collectionId });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!document) return <LoadingState label="loading document…" />;

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%", display: "flex", flexDirection: "column" }}>
      <BackLink label="Documents" onClick={() => onNavigate({ name: "collection-documents", collectionId })} />
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, margin: `${theme.space.s}px 0` }}>
        <h1 style={{ fontSize: theme.font.size.xl, wordBreak: "break-word" }}>{document.filename}</h1>
        <DocumentStatusChip status={document.status} />
        {!document.enabled && <Chip tone="warn">disabled</Chip>}
        <DocumentEnabledToggle documentId={documentId} enabled={document.enabled} onChanged={handleDocumentEnabledChanged} />
      </div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, marginBottom: theme.space.m }}>
        {document.format.toUpperCase()} · {document.page_count ?? "—"} page(s) · {formatBytes(document.file_size)} · created {formatDateTime(document.created_at)}
      </div>

      <div style={{ marginBottom: theme.space.m }}>
        {confirmingDelete ? (
          <span style={{ display: "inline-flex", gap: theme.space.s, alignItems: "center" }}>
            <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>Delete for good?</span>
            <Button variant="danger" disabled={deleting} onClick={handleDelete}>{deleting ? "deleting…" : "Confirm delete"}</Button>
            <Button onClick={() => setConfirmingDelete(false)}>Cancel</Button>
          </span>
        ) : (
          <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete document</Button>
        )}
      </div>

      <TabNav tabs={TABS} active={activeTab} onSelect={setActiveTab} />

      <div style={{ marginTop: theme.space.m, flex: 1, minHeight: 0 }}>
        {activeTab === "overview" && <OverviewTab document={document} />}
        {activeTab === "pages" &&
          (pagesError ? (
            <ErrorState message={pagesError} onRetry={loadPages} />
          ) : pages ? (
            <PagesTab pages={pages} />
          ) : (
            <LoadingState label="loading pages…" />
          ))}
        {activeTab === "ir" &&
          (irError ? (
            <ErrorState message={irError} onRetry={loadIr} />
          ) : ir ? (
            <IRTab ir={ir} focusBlockId={focusBlockId} />
          ) : (
            <LoadingState label="loading IR…" />
          ))}
        {activeTab === "chunks" &&
          (chunksError ? (
            <ErrorState message={chunksError} onRetry={loadChunks} />
          ) : chunks ? (
            <ChunksTab chunks={chunks} onJumpToBlock={jumpToBlock} onChunkEnabledChanged={handleChunkEnabledChanged} />
          ) : (
            <LoadingState label="loading chunks…" />
          ))}
      </div>
    </div>
  );
}
