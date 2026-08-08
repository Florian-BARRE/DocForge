// ====== Code Summary ======
// Per-tab lazy fetch for the document page: Pages/IR/Chunks are each fetched once, the first time
// their tab is activated, and cached here for as long as the page stays mounted (navigating to a
// different document remounts the page — see the app's "page remount = free refetch" convention).
// Also owns resolving a chunk to its source page + block boxes for the "view on page" overlay,
// since that join needs both IR and Pages loaded regardless of which of the two unlocked it.

import { useEffect, useState } from "react";
import {
  getDocumentChunks, getDocumentIR, getDocumentPages,
  type ChunkInfo, type DocumentIR, type PageInfo,
} from "../../../api/explorer";
import type { OverlayBox } from "../../../components/PageBoxOverlay";
import { useToast } from "../../../shell/toast";
import { displayPage } from "../format";

export type DocumentTabKey = "overview" | "pages" | "ir" | "chunks";

export interface BoxLightboxState {
  renderBlobHash: string | null;
  width: number | null;
  height: number | null;
  boxes: OverlayBox[];
  caption: string;
}

export function useDocumentTabs(documentId: string, activeTab: DocumentTabKey) {
  const toast = useToast();
  const [pages, setPages] = useState<PageInfo[] | null>(null);
  const [pagesError, setPagesError] = useState<string | null>(null);
  const [ir, setIr] = useState<DocumentIR | null>(null);
  const [irError, setIrError] = useState<string | null>(null);
  const [chunks, setChunks] = useState<ChunkInfo[] | null>(null);
  const [chunksError, setChunksError] = useState<string | null>(null);
  const [boxLightbox, setBoxLightbox] = useState<BoxLightboxState | null>(null);

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

  const handleChunkEnabledChanged = (chunkId: string, enabled: boolean) => {
    setChunks((prev) => (prev ? prev.map((chunk) => (chunk.id === chunkId ? { ...chunk, enabled } : chunk)) : prev));
  };

  return {
    pages, pagesError, loadPages,
    ir, irError, loadIr,
    chunks, chunksError, loadChunks, handleChunkEnabledChanged,
    chunkLocator,
    boxLightbox, closeBoxLightbox: () => setBoxLightbox(null),
  };
}
