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
import { PageBoxLightbox } from "../../components/PageBoxLightbox";
import type { OverlayBox } from "../../components/PageBoxOverlay";
import { PageHeader } from "../../components/PageHeader";
import { TabNav } from "../../components/TabNav";
import type { Navigate } from "../../shell/view";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";
import { ChunksTab } from "./chunks/ChunksTab";
import { DocumentEnabledToggle } from "./DocumentEnabledToggle";
import { DocumentStatusChip } from "./DocumentStatusChip";
import { displayPage, formatBytes, formatDateTime } from "./format";
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

interface BoxLightboxState {
  renderBlobHash: string | null;
  width: number | null;
  height: number | null;
  boxes: OverlayBox[];
  caption: string;
}

export function DocumentPage({ collectionId, documentId, onNavigate }: DocumentPageProps) {
  const toast = useToast();
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [focusBlockId, setFocusBlockId] = useState<string | null>(null);
  const [boxLightbox, setBoxLightbox] = useState<BoxLightboxState | null>(null);

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

  // Fetch each tab's payload once, the first time it is activated — never all four upfront. The
  // chunks tab additionally warms pages + IR so a chunk can be located on its source page (the
  // "view on page" box overlay joins chunk.block_ids → IR block bbox → the page render).
  useEffect(() => {
    if (activeTab === "pages" && pages === null && !pagesError) loadPages();
    if (activeTab === "ir" && ir === null && !irError) loadIr();
    if (activeTab === "chunks") {
      if (chunks === null && !chunksError) loadChunks();
      if (pages === null && !pagesError) loadPages();
      if (ir === null && !irError) loadIr();
    }
    // Deliberately reacting only to the tab/document — the load* functions themselves are stable
    // enough for this effect's purpose (avoid a re-run loop on every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, documentId]);

  // Resolve a chunk to its source page + block boxes and open the overlay. Requires IR + pages
  // (only offered to the chunk card once both are loaded). The chunk may span pages — we show its
  // leading block's page with a box around every block that sits on that same page.
  const showChunkOnPage = (chunk: ChunkInfo) => {
    if (!ir || !pages) return;
    const blocks = chunk.block_ids
      .map((id) => ir.blocks.find((block) => block.id === id))
      .filter((block): block is NonNullable<typeof block> => Boolean(block));
    if (!blocks.length) {
      toast.info("This chunk has no located source blocks.");
      return;
    }
    const targetPage = blocks[0].page;
    const boxes: OverlayBox[] = blocks.filter((block) => block.page === targetPage).map((block) => ({ bbox: block.bbox }));
    const page = pages.find((p) => p.page_number === targetPage) ?? null;
    setBoxLightbox({
      renderBlobHash: page?.render_blob_hash ?? null,
      width: page?.width ?? null,
      height: page?.height ?? null,
      boxes,
      caption: `Page ${displayPage(targetPage)} · chunk #${chunk.chunk_index}`,
    });
  };
  const chunkLocator = ir && pages ? showChunkOnPage : undefined;

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
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", display: "flex", flexDirection: "column", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
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
          <>
            <DocumentEnabledToggle documentId={documentId} enabled={document.enabled} onChanged={handleDocumentEnabledChanged} />
            {confirmingDelete ? (
              <span style={{ display: "inline-flex", gap: theme.space.s, alignItems: "center" }}>
                <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>Delete for good?</span>
                <Button variant="danger" disabled={deleting} onClick={handleDelete}>{deleting ? "deleting…" : "Confirm delete"}</Button>
                <Button onClick={() => setConfirmingDelete(false)}>Cancel</Button>
              </span>
            ) : (
              <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete document</Button>
            )}
          </>
        }
      />

      <TabNav tabs={TABS} active={activeTab} onSelect={setActiveTab} />

      <div style={{ marginTop: theme.space.l, flex: 1, minHeight: 0 }}>
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
            <ChunksTab chunks={chunks} onJumpToBlock={jumpToBlock} onChunkEnabledChanged={handleChunkEnabledChanged} onShowChunkOnPage={chunkLocator} />
          ) : (
            <LoadingState label="loading chunks…" />
          ))}
      </div>

      {boxLightbox && (
        <PageBoxLightbox
          renderBlobHash={boxLightbox.renderBlobHash}
          width={boxLightbox.width}
          height={boxLightbox.height}
          boxes={boxLightbox.boxes}
          caption={boxLightbox.caption}
          onClose={() => setBoxLightbox(null)}
        />
      )}
    </div>
  );
}
