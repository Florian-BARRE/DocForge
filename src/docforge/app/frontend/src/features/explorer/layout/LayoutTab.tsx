// ====== Code Summary ======
// The Layout tab — the visual, at-a-glance view of a parsed document: every page render with its
// detected blocks drawn as colour-coded, numbered boxes, beside a reading-order panel showing each
// block's content and enrichment. It reuses the IR (blocks + enrichments) and pages the other tabs
// already load; here they are joined per page. A calmer, whole-document alternative to scrolling the
// flat IR list — the raw IR and Chunks tabs remain untouched for detail work.

import { useMemo } from "react";

import type { ChunkInfo, DocumentIR, DocumentProvenance, IREnrichment, IRTable, PageInfo } from "../../../api/explorer";
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
  /** A chunks-only fetch failure — non-blocking: the page/IR view still renders, chunk grouping
   *  and provenance are simply absent (mirrors the "chunks are optional context" comment below). */
  chunksError: string | null;
  onRetry: () => void;
  onRetryChunks: () => void;
}

export function LayoutTab({ ir, pages, chunks, provenance, error, chunksError, onRetry, onRetryChunks }: LayoutTabProps) {
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

  // Table blocks keyed by id — the Chunk column's provenance segmentation re-renders each table's
  // markdown grid (the chunker's actual embedded text) to attribute it to its TABLE block, not glue.
  const tablesByBlock = useMemo(() => {
    const map = new Map<string, IRTable>();
    for (const table of ir?.tables ?? []) map.set(table.block_id, table);
    return map;
  }, [ir]);

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
    // Gate on the PARSE stage, not just the kind: several kinds (e.g. "mistral", "dots_ocr") are
    // shared across families — a (ocr, mistral) crop-reader runs in ENRICH, a (llm, …) in
    // contextualize/metagen — so a kind-only match would misclassify them as parsers. Only a node
    // whose pipeline stage is "parse" is part of the extraction chain.
    const chain = (provenance?.stages ?? [])
      .filter((stage) => stage.stage === "parse" && stage.node_kind && PARSERS.has(stage.node_kind))
      .map((stage) => ({ kind: stage.node_kind as string, status: stage.status }));
    if (chain.length > 0) return chain;
    const fallback = provenance?.stages.find((stage) => stage.stage === "parse")?.node_kind;
    return fallback ? [{ kind: fallback, status: "success" }] : [];
  }, [provenance]);

  // Scrubber entries + row anchor ids, computed once per pageGroups change instead of twice per
  // render (once for the scrubber, once per row for its own anchor id).
  const pageGroupNavs = useMemo(() => pageGroups.map(pageGroupNav), [pageGroups]);

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
      {chunksError && (
        <div
          role="status"
          style={{
            display: "flex",
            alignItems: "center",
            gap: theme.space.s,
            fontSize: theme.font.size.s,
            color: theme.color.warnStrong,
            background: theme.color.warnSoft,
            border: `1px solid ${theme.color.warn}`,
            borderRadius: theme.radius.m,
            padding: `${theme.space.s}px ${theme.space.m}px`,
          }}
        >
          <span>Chunk provenance is unavailable ({chunksError}) — showing pages and IR only.</span>
          <button
            type="button"
            onClick={onRetryChunks}
            style={{
              fontSize: theme.font.size.xs,
              color: theme.color.warnStrong,
              background: "none",
              border: "none",
              textDecoration: "underline",
              cursor: "pointer",
              padding: 0,
            }}
          >
            retry
          </button>
        </div>
      )}
      <PageScrubber entries={pageGroupNavs} />
      <BlockTypeLegend />
      {pageGroups.map((group, index) => (
        <PageGroupRow
          key={group.pages[0].page_number}
          rowId={pageGroupNavs[index].id}
          pages={group.pages}
          blocks={group.blocks}
          enrichmentsByBlock={enrichmentsByBlock}
          tablesByBlock={tablesByBlock}
          chunkByBlockId={chunkByBlockId}
          parseChain={parseChain}
        />
      ))}
    </div>
  );
}
