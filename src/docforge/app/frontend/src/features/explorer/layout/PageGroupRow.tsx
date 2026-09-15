// ====== Code Summary ======
// One ROW of the Layout view — usually a single page, but when a chunk spans a page boundary the two
// (or more) pages it bridges share a row so the transition is inspected whole. Read LEFT → RIGHT (or
// TOP → BOTTOM once the row stacks — see below):
//   • PAGE   — every page render in the row, stacked, each block boxed/numbered/coloured by IR type,
//     with a dashed chunk-outline-coloured container box per chunk (the spanning chunk's outline
//     appears on BOTH pages, showing it continue across). Every box is clickable. Sized by the shared
//     page-zoom control (pageZoom.ts) rather than a fixed viewport-height cap.
//   • GRAPH  — the connected IR↔chunk flow (IrChunkGraph): every IR block in reading order, tied by a
//     Sankey ribbon to the chunk it was folded into.
// Selection (a block or a chunk) is shared across both regions and every page in the row.
//
// RESPONSIVE: side-by-side needs the page column PLUS the graph's own minimum width (its fixed-width
// chunk column + connector) to both fit without squeezing the chunk column into an unreadable sliver
// that then scrolls sideways — below `ROW_STACK_BREAKPOINT_PX` the row STACKS instead (page on top,
// full width; graph below, full width, its chunk column rendered at its real size).

import { useMemo, useState } from "react";

import type { ChunkInfo, IRBlock, IREnrichment, IRTable, PageInfo } from "../../../api/explorer";
import { PageBoxOverlay, type OverlayBox } from "../../../components/PageBoxOverlay";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { blockStyle } from "./blockColors";
import { pageBlocksLackLayout, unionBbox } from "./chunkGrouping";
import { IrChunkGraph } from "./IrChunkGraph";
import { shouldStackColumns } from "./layoutBreakpoint";
import { computeTargetWidthPx, type PageZoomState } from "./pageZoom";
import { useContainerWidth } from "./useContainerWidth";

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

type Selection = { kind: "block" | "chunk"; id: string };

// Below this, the page column can no longer sit beside the graph without squeezing its fixed-width
// chunk column — see layoutBreakpoint.ts.
const CHUNK_WIDTH_COMPACT = 384; // side-by-side — unchanged historical width
const CHUNK_WIDTH_WIDE = 460; // stacked — the graph gets the full row, give its cards more measure
// A sane pre-measurement default (before the column's ResizeObserver reports in) — close to the
// compact chunk column's historical visual width, avoids a jarring first-paint jump.
const DEFAULT_COLUMN_WIDTH_PX = 560;

export function PageGroupRow({ pages, blocks, enrichmentsByBlock, tablesByBlock, chunkByBlockId, parseChain, rowId, pageZoom }: PageGroupRowProps) {
  const [selected, setSelected] = useState<Selection | null>(null);
  const [rowRef, rowWidth] = useContainerWidth<HTMLElement>();
  const [pageColRef, pageColWidth] = useContainerWidth<HTMLDivElement>();

  const selectBlock = (id: string) =>
    setSelected((prev) => (prev?.kind === "block" && prev.id === id ? null : { kind: "block", id }));
  const selectChunk = (id: string) =>
    setSelected((prev) => (prev?.kind === "chunk" && prev.id === id ? null : { kind: "chunk", id }));

  const selectedBlockId = selected?.kind === "block" ? selected.id : null;
  const activeChunkId =
    selected?.kind === "chunk"
      ? selected.id
      : selectedBlockId
        ? chunkByBlockId.get(selectedBlockId)?.id ?? null
        : null;
  // The block's number is its position in the row's continuous reading order — shared by the page box
  // badge and the middle card so they always agree.
  const indexByBlockId = useMemo(() => {
    const map = new Map<string, number>();
    blocks.forEach((block, index) => map.set(block.id, index));
    return map;
  }, [blocks]);

  // The chunks present in this row, in first-appearance order (drives the right column).
  const chunksInRow = useMemo(() => {
    const seen = new Set<string>();
    const ordered: ChunkInfo[] = [];
    for (const block of blocks) {
      const chunk = chunkByBlockId.get(block.id);
      if (chunk && !seen.has(chunk.id)) {
        seen.add(chunk.id);
        ordered.push(chunk);
      }
    }
    return ordered;
  }, [blocks, chunkByBlockId]);

  const hasSelection = selected != null;
  // Nudge a block box outward so its border floats just OFF the glyphs instead of cutting through them.
  const padOut = (bb: number[], d = 0.005): number[] => [bb[0] - d, bb[1] - d, bb[2] + d, bb[3] + d];

  // A page whose blocks carry no real positional layout (a page-less html/md parse — see
  // chunkGrouping.ts) would only draw indistinguishable full-page boxes on top of each other; this
  // set flags those pages so `boxesByPage` skips them and the render below shows an honest note
  // instead of a confusing stack of rectangles.
  const noLayoutPages = useMemo(() => {
    const set = new Set<number>();
    for (const page of pages) {
      const pageBlocks = blocks.filter((b) => b.page === page.page_number);
      if (pageBlocksLackLayout(pageBlocks)) set.add(page.page_number);
    }
    return set;
  }, [pages, blocks]);

  // Build the overlay boxes for every page in the row, once per relevant change (not on every
  // render — a row can hold many blocks, and this used to re-filter/re-map all of them on every
  // unrelated render). COLOUR = IR TYPE (same hue as the block's card + its segment in the chunk —
  // one colour means one thing everywhere); body Text stays neutral so a page isn't a rainbow, only
  // the notable types pop. CHUNK GROUPING is a neutral dashed outline that carries an always-on,
  // subtle "Cn" tag (PageBoxOverlay) even at idle — so a document reads as chunked without a click —
  // and a spanning chunk draws it on both pages. The forge accent is reserved for the active one;
  // everything outside the current selection dims.
  const boxesByPage = useMemo(() => {
    const map = new Map<number, OverlayBox[]>();
    for (const page of pages) {
      const pageNumber = page.page_number;
      if (noLayoutPages.has(pageNumber)) {
        map.set(pageNumber, []);
        continue;
      }
      const pageBlocks = blocks.filter((b) => b.page === pageNumber);

      const byChunk = new Map<string, { chunk: ChunkInfo; bboxes: number[][] }>();
      for (const block of pageBlocks) {
        const chunk = chunkByBlockId.get(block.id);
        if (!chunk) continue;
        const entry = byChunk.get(chunk.id) ?? { chunk, bboxes: [] };
        entry.bboxes.push(block.bbox);
        byChunk.set(chunk.id, entry);
      }
      const groupBoxes: OverlayBox[] = [...byChunk.values()].map(({ chunk, bboxes }) => {
        const active = activeChunkId === chunk.id;
        return {
          bbox: unionBbox(bboxes, 0.012),
          color: active ? theme.color.accent : theme.color.chunkOutline,
          // Idle carries a compact "Cn" tag (subtle outlined chip, see PageBoxOverlay); active gets
          // the bolder full "Chunk N" tab — either way the label is never withheld at rest anymore.
          label: active ? `Chunk ${chunk.chunk_index}` : `C${chunk.chunk_index}`,
          active,
          dim: hasSelection && !active,
          variant: "group" as const,
          onSelect: () => selectChunk(chunk.id),
          selectLabel: `Chunk ${chunk.chunk_index}`,
        };
      });

      const blockBoxes: OverlayBox[] = pageBlocks.map((block) => {
        const chunk = chunkByBlockId.get(block.id);
        const active = selectedBlockId === block.id || (chunk != null && chunk.id === activeChunkId);
        const index = indexByBlockId.get(block.id) ?? 0;
        return {
          bbox: padOut(block.bbox),
          color: active ? theme.color.accent : blockStyle(block.block_type).color,
          // The number tab sits ABOVE the box's corner (never over the page content), so every block
          // carries its reading-order number — this is what lets the eye map a page box to its card
          // in the numbered IR-blocks column. During a chunk/block selection the non-active boxes
          // dim, and a dimmed box hides its label, so the selection still reads cleanly.
          label: String(index + 1),
          active,
          dim: hasSelection && !active,
          variant: "block" as const,
          onSelect: () => selectBlock(block.id),
          selectLabel: `Block ${index + 1}, ${blockStyle(block.block_type).label}`,
        };
      });

      map.set(pageNumber, [...groupBoxes, ...blockBoxes]);
    }
    return map;
  }, [pages, blocks, chunkByBlockId, activeChunkId, selectedBlockId, hasSelection, indexByBlockId, noLayoutPages]);

  // Below the breakpoint, neither the page column nor the graph's fixed-width chunk column have room
  // to render at a legible size side by side — stack them instead, each at the row's full width.
  const stacked = shouldStackColumns(rowWidth);
  const chunkWidth = stacked ? CHUNK_WIDTH_WIDE : CHUNK_WIDTH_COMPACT;
  const columnWidthPx = pageColWidth || DEFAULT_COLUMN_WIDTH_PX;

  return (
    <section
      id={rowId}
      ref={rowRef}
      style={{
        display: "grid",
        // The page render is the primary subject — its column is sized so the image FILLS it (width
        // then binds, no dead strip beside a height-capped image), while still leaving the IR↔chunk
        // graph more than its min-width so it never has to scroll sideways. Below the breakpoint the
        // two stack into a single full-width column instead (grid auto-flow already stacks rows).
        gridTemplateColumns: stacked ? "1fr" : "minmax(420px, 620px) minmax(0, 1fr)",
        gap: theme.space.l,
        // Multi-page group, side-by-side: stretch the page column to the graph's height so the page
        // renders SPREAD down beside the blocks they belong to. Stacked or single-page: top-aligned.
        alignItems: !stacked && pages.length > 1 ? "stretch" : "start",
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
          stacked
            ? { display: "flex", flexDirection: "column", gap: theme.space.m }
            : pages.length > 1
              ? { display: "flex", flexDirection: "column", justifyContent: "space-between", gap: theme.space.m }
              : { position: "sticky", top: theme.space.m, display: "flex", flexDirection: "column", gap: theme.space.m }
        }
      >
        {pages.map((page) => {
          const targetWidthPx = computeTargetWidthPx(pageZoom, page.width, page.height, columnWidthPx);
          return (
            <div key={page.page_number} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
              <div style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, color: theme.color.text }}>
                Page {displayPage(page.page_number)}
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
                  alt={`Page ${displayPage(page.page_number)} layout`}
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

      {/* GRAPH — the connected IR ↔ chunk flow (continuous across the row's pages). */}
      <IrChunkGraph
        blocks={blocks}
        chunks={chunksInRow}
        enrichmentsByBlock={enrichmentsByBlock}
        tablesByBlock={tablesByBlock}
        chunkByBlockId={chunkByBlockId}
        selectedBlockId={selectedBlockId}
        activeChunkId={activeChunkId}
        parseChain={parseChain}
        chunkWidth={chunkWidth}
        onSelectBlock={selectBlock}
        onSelectChunk={selectChunk}
      />
    </section>
  );
}
