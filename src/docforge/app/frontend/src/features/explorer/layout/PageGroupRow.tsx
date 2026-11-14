// ====== Code Summary ======
// One ROW of the Layout view — usually a single page, but when a chunk spans a page boundary the two
// (or more) pages it bridges share a row so the transition is inspected whole. Read LEFT → RIGHT,
// ALWAYS side by side, on every viewport (a responsive vertical stack was tried and rejected — on a
// tall text-heavy page it pushed the IR/chunk lanes far below the fold, effectively hiding them):
//   • PAGE   — every page render in the row, stacked, each block boxed/numbered/coloured by IR type,
//     with a dashed chunk-outline-coloured container box per chunk (the spanning chunk's outline
//     appears on BOTH pages, showing it continue across). Every box is clickable. Sized by the shared
//     page-zoom control (pageZoom.ts) rather than a fixed viewport-height cap.
//   • GRAPH  — the connected IR↔chunk flow (IrChunkGraph): the IR-blocks lane sits close to the page
//     (small gap, capped width — it's a supporting lane, not the main subject) and the chunk lane
//     sits comfortably wide on the far right, tied by a Sankey ribbon.
// Selection (a block or a chunk) is shared across both regions and every page in the row.
//
// NARROW VIEWPORTS: the three lanes never stack and the page body never scrolls sideways — the graph
// (IR + chunk lanes) has its OWN horizontal scroll wrapper (IrChunkGraph) once its fixed total width
// no longer fits its grid track; the page lane shrinks within its own `minmax` band first.

import type { ChunkInfo, IRBlock, IREnrichment, IRTable, PageInfo } from "../../../api/explorer";
import { PageBoxOverlay } from "../../../components/PageBoxOverlay";
import { theme } from "../../../theme";
import { IrChunkGraph } from "./IrChunkGraph";
import {
  CHUNK_COLUMN_WIDTH_PX,
  DEFAULT_COLUMN_WIDTH_PX,
  IR_COLUMN_WIDTH_PX,
  PAGE_COLUMN_MAX_PX,
  PAGE_COLUMN_MIN_PX,
} from "./pageGroupModel";
import { computeTargetWidthPx, type PageZoomState } from "./pageZoom";
import { useContainerWidth } from "./useContainerWidth";
import { usePageGroupRow } from "./usePageGroupRow";
import { pageLabelOf } from "../format";

interface PageGroupRowProps {
  pages: PageInfo[];
  blocks: IRBlock[];
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  tablesByBlock: Map<string, IRTable>;
  chunkByBlockId: Map<string, ChunkInfo>;
  /** The parser chain that produced the IR (with fallback outcomes) — extraction provenance per block. */
  parseChain: { kind: string; status: string }[];
  /** DOM id anchor so the page navigator can scroll this row into view. */
  rowId: string;
  /** The shared page-zoom choice (one control above the whole tab) driving every page's width. */
  pageZoom: PageZoomState;
}

export function PageGroupRow({ pages, blocks, enrichmentsByBlock, tablesByBlock, chunkByBlockId, parseChain, rowId, pageZoom }: PageGroupRowProps) {
  const [pageColRef, pageColWidth] = useContainerWidth<HTMLDivElement>();
  const { selectedBlockId, activeChunkId, chunksInRow, noLayoutPages, boxesByPage, selectBlock, selectChunk } =
    usePageGroupRow(pages, blocks, chunkByBlockId);

  const columnWidthPx = pageColWidth || DEFAULT_COLUMN_WIDTH_PX;

  return (
    <section
      id={rowId}
      style={{
        display: "grid",
        // ALWAYS side by side — page column, then the graph (IR + chunk lanes). The page column is
        // readable but capped so the graph keeps real room beside it; the graph itself never grows
        // past its own fixed total width (IrChunkGraph), so a wide viewport doesn't inflate the IR
        // lane, and a narrow one scrolls the graph horizontally WITHIN itself, never the row/page.
        gridTemplateColumns: `minmax(${PAGE_COLUMN_MIN_PX}px, ${PAGE_COLUMN_MAX_PX}px) minmax(0, 1fr)`,
        // Tight on purpose — the IR lane should read as sitting close to its source page, not floating
        // in a wide gutter (feedback: "bring it CLOSER to the page image").
        gap: theme.space.s,
        // Multi-page group: stretch the page column to the graph's height so the page renders SPREAD
        // down beside the blocks they belong to (justify below) instead of pooling the empty space in
        // one dead block bottom-left. Single page: keep it top-aligned so its lone render can stick.
        alignItems: pages.length > 1 ? "stretch" : "start",
        borderTop: `1px solid ${theme.color.line}`,
        paddingTop: theme.space.l,
        // Clear the sticky page navigator when scrolled to via a nav chip.
        scrollMarginTop: 52,
      }}
    >
      {/* PAGE — every page in the row, stacked so a spanning chunk's two pages are seen together. */}
      <div
        ref={pageColRef}
        style={
          pages.length > 1
            ? { display: "flex", flexDirection: "column", justifyContent: "space-between", gap: theme.space.m }
            : { position: "sticky", top: theme.space.m, display: "flex", flexDirection: "column", gap: theme.space.m }
        }
      >
        {pages.map((page) => {
          const targetWidthPx = computeTargetWidthPx(pageZoom, page.width, page.height, columnWidthPx);
          return (
            <div key={page.page_number} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
              <div style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, color: theme.color.text }}>
                Page {pageLabelOf(page)}
                <span style={{ color: theme.color.mute, fontWeight: theme.font.weight.normal }}>
                  {" "}
                  · {blocks.filter((b) => b.page === page.page_number).length} blocks
                </span>
              </div>
              {/* `overflowX: auto` is a no-op when the target width fits the column — it only kicks
                  in once a zoom step pushes the image past it, so zooming in never breaks the grid. */}
              <div style={{ overflowX: "auto" }}>
                <PageBoxOverlay
                  renderBlobHash={page.render_blob_hash}
                  width={page.width}
                  height={page.height}
                  boxes={boxesByPage.get(page.page_number) ?? []}
                  alt={`Page ${pageLabelOf(page)} layout`}
                  style={{ width: targetWidthPx, height: "auto" }}
                  // The Layout tab can render a whole document's pages at once — defer each page's
                  // fetch until it scrolls near view instead of firing one request per page up front.
                  lazy
                />
              </div>
              {noLayoutPages.has(page.page_number) && (
                <div style={{ fontSize: theme.font.size.xs, color: theme.color.mute, fontStyle: "italic" }}>
                  No positional layout for this page (parsed from a page-less format) — chunk regions
                  can't be located on it.
                </div>
              )}
            </div>
          );
        })}
        <span style={{ fontSize: theme.font.size.xs, color: theme.color.mute }}>
          Click any block or chunk to trace it across the columns.
        </span>
      </div>

      {/* GRAPH — the connected IR ↔ chunk flow (continuous across the row's pages). Always beside the
          page, never below it — see IrChunkGraph for its own fixed width + horizontal scroll. */}
      <IrChunkGraph
        blocks={blocks}
        chunks={chunksInRow}
        enrichmentsByBlock={enrichmentsByBlock}
        tablesByBlock={tablesByBlock}
        chunkByBlockId={chunkByBlockId}
        selectedBlockId={selectedBlockId}
        activeChunkId={activeChunkId}
        parseChain={parseChain}
        irWidth={IR_COLUMN_WIDTH_PX}
        chunkWidth={CHUNK_COLUMN_WIDTH_PX}
        onSelectBlock={selectBlock}
        onSelectChunk={selectChunk}
      />
    </section>
  );
}
