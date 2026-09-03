// ====== Code Summary ======
// The Layout tab — the visual, at-a-glance view of a parsed document: every page render with its
// detected blocks drawn as colour-coded, numbered boxes, beside a reading-order panel showing each
// block's content and enrichment. It reuses the IR (blocks + enrichments) and pages the other tabs
// already load; here they are joined per page. A calmer, whole-document alternative to scrolling the
// flat IR list — the raw IR and Chunks tabs remain untouched for detail work.

import { useMemo } from "react";

import type { ChunkInfo, DocumentIR, DocumentProvenance, IREnrichment, PageInfo } from "../../../api/explorer";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { BlockTypeLegend } from "./BlockTypeLegend";
import { buildChunkByBlockId, buildPageGroups } from "./chunkGrouping";
import { PageGroupRow } from "./PageGroupRow";
import { PageScrubber, type PageScrubEntry } from "./PageScrubber";

/** Anchor id + short label ("3" or "3–4") for a page group, shared by the scrubber and its row. */
function pageGroupNav(group: { pages: { page_number: number }[] }): PageScrubEntry {
  const first = group.pages[0].page_number;
  const last = group.pages[group.pages.length - 1].page_number;
  const label = group.pages.length > 1 ? `${displayPage(first)}–${displayPage(last)}` : `${displayPage(first)}`;
  return { id: `layout-pg-${first}`, label };
}

interface LayoutTabProps {
  ir: DocumentIR | null;
  pages: PageInfo[] | null;
  chunks: ChunkInfo[] | null;
  provenance: DocumentProvenance | null;
  error: string | null;
  onRetry: () => void;
}

export function LayoutTab({ ir, pages, chunks, provenance, error, onRetry }: LayoutTabProps) {
  // Group enrichments by block once, and blocks by page (in reading order), so each PageLayoutRow
  // gets exactly its slice with no per-row scanning of the whole IR.
  const enrichmentsByBlock = useMemo(() => {
    const map = new Map<string, IREnrichment[]>();
    for (const enrichment of ir?.enrichments ?? []) {
      const list = map.get(enrichment.block_id);
      if (list) list.push(enrichment);
      else map.set(enrichment.block_id, [enrichment]);
    }
    return map;
  }, [ir]);

  // Chunks are optional context (the panel groups by them but still renders without them) — an empty
  // map when chunks failed or are still loading, so a chunks hiccup never blocks the layout.
  const chunkByBlockId = useMemo(() => buildChunkByBlockId(chunks ?? []), [chunks]);

  // Pages joined by a chunk that spans them become ONE row (so a cross-page chunk is inspected whole,
  // both pages visible at once); un-bridged pages stay solo.
  const pageGroups = useMemo(
    () => (ir && pages ? buildPageGroups(pages, ir.blocks, chunks ?? []) : []),
    [ir, pages, chunks],
  );

  // The parser CHAIN that produced the IR — surfaced ON each block (extraction provenance), NOT as a
  // separate pipeline panel. Every parse-family stage the pipeline ran, in order, with its outcome —
  // so a fallback/escalation (e.g. docling failed → pp_structure succeeded) is visible per block.
  const parseChain = useMemo(() => {
    const PARSERS = new Set(["docling", "granite_docling", "pp_structure", "mineru", "marker", "dots_ocr", "azure", "mistral"]);
    const chain = (provenance?.stages ?? [])
      .filter((stage) => stage.node_kind && PARSERS.has(stage.node_kind))
      .map((stage) => ({ kind: stage.node_kind as string, status: stage.status }));
    if (chain.length > 0) return chain;
    const fallback = provenance?.stages.find((stage) => stage.stage === "parse")?.node_kind;
    return fallback ? [{ kind: fallback, status: "success" }] : [];
  }, [provenance]);

  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (ir === null || pages === null) return <LoadingState label="loading layout…" />;
  if (pageGroups.length === 0) {
    return (
      <EmptyState
        icon="▦"
        title="No layout to show"
        subtitle="This document has no located blocks — its pages were not rasterised, or parsing produced no positioned content."
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      <PageScrubber entries={pageGroups.map(pageGroupNav)} />
      <BlockTypeLegend />
      {pageGroups.map((group) => (
        <PageGroupRow
          key={group.pages[0].page_number}
          rowId={pageGroupNav(group).id}
          pages={group.pages}
          blocks={group.blocks}
          enrichmentsByBlock={enrichmentsByBlock}
          chunkByBlockId={chunkByBlockId}
          parseChain={parseChain}
        />
      ))}
    </div>
  );
}
