// ====== Code Summary ======
// One ROW of the Layout view — usually a single page, but when a chunk spans a page boundary the two
// (or more) pages it bridges share a row so the transition is inspected whole. Read LEFT → RIGHT:
//   • LEFT   — every page render in the row, stacked, each block boxed/numbered/coloured by IR type
//     with a solid lane-coloured outline per chunk (the spanning chunk's outline appears on BOTH pages,
//     showing it continue across). Every box is clickable.
//   • MIDDLE — every IR block in ONE continuous reading-order list across the row's pages, with a page
//     divider at each boundary, so a spanning chunk's blocks stay adjacent.
//   • RIGHT  — each chunk in full, centred on its member blocks, tied by an organic flow ribbon.
// Selection (a block or a chunk) is shared across all three columns and every page in the row.

import { useMemo, useState } from "react";

import type { ChunkInfo, IRBlock, IREnrichment, PageInfo } from "../../../api/explorer";
import { PageBoxOverlay, type OverlayBox } from "../../../components/PageBoxOverlay";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { blockStyle } from "./blockColors";
import { unionBbox } from "./chunkGrouping";
import { IrChunkGraph } from "./IrChunkGraph";

interface PageGroupRowProps {
  pages: PageInfo[];
  blocks: IRBlock[];
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  chunkByBlockId: Map<string, ChunkInfo>;
  /** The parser chain that produced the IR (with fallback outcomes) — extraction provenance per block. */
  parseChain: { kind: string; status: string }[];
  /** DOM id anchor so the page navigator can scroll this row into view. */
  rowId: string;
}

type Selection = { kind: "block" | "chunk"; id: string };

export function PageGroupRow({ pages, blocks, enrichmentsByBlock, chunkByBlockId, parseChain, rowId }: PageGroupRowProps) {
  const [selected, setSelected] = useState<Selection | null>(null);

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

  // The chunks present in this row, in first-appearance order (the right column + lane colours).
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

  // Build the overlay boxes for one page. COLOUR = IR TYPE (same hue as the block's card + its segment
  // in the chunk — one colour means one thing everywhere); body Text stays neutral so a page isn't a
  // rainbow, only the notable types pop. CHUNK GROUPING is a neutral rounded outline (badged Cn) — a
  // spanning chunk draws it on both pages. The forge accent is reserved for the active one; everything
  // outside the current selection dims. Per-block numbers show only when active (idle stays clean).
  const boxesForPage = (pageNumber: number): OverlayBox[] => {
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
        label: `Chunk ${chunk.chunk_index}`,
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
        label: String(index + 1),
        active,
        dim: hasSelection && !active,
        variant: "block" as const,
        onSelect: () => selectBlock(block.id),
        selectLabel: `Block ${index + 1}, ${blockStyle(block.block_type).label}`,
      };
    });

    return [...groupBoxes, ...blockBoxes];
  };

  const maxPageHeight = pages.length > 1 ? `${Math.floor(80 / pages.length)}vh` : "82vh";

  return (
    <section
      id={rowId}
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(200px, 320px) minmax(0, 1fr)",
        gap: theme.space.l,
        alignItems: "start",
        borderTop: `1px solid ${theme.color.line}`,
        paddingTop: theme.space.l,
        // Clear the sticky page navigator when scrolled to via a nav chip.
        scrollMarginTop: 52,
      }}
    >
      {/* LEFT — every page in the row, stacked so a spanning chunk's two pages are seen together. */}
      <div style={{ position: "sticky", top: theme.space.m, display: "flex", flexDirection: "column", gap: theme.space.m }}>
        {pages.map((page) => (
          <div key={page.page_number} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
            <div style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, color: theme.color.text }}>
              Page {displayPage(page.page_number)}
              <span style={{ color: theme.color.mute, fontWeight: theme.font.weight.normal }}>
                {" "}
                · {blocks.filter((b) => b.page === page.page_number).length} blocks
              </span>
            </div>
            <PageBoxOverlay
              renderBlobHash={page.render_blob_hash}
              width={page.width}
              height={page.height}
              boxes={boxesForPage(page.page_number)}
              alt={`Page ${displayPage(page.page_number)} layout`}
              style={{ maxWidth: "100%", maxHeight: maxPageHeight }}
            />
          </div>
        ))}
        <span style={{ fontSize: theme.font.size.xs, color: theme.color.mute }}>
          Click any block or chunk to trace it across the columns.
        </span>
      </div>

      {/* MIDDLE + RIGHT — the connected IR ↔ chunk flow (continuous across the row's pages). */}
      <IrChunkGraph
        blocks={blocks}
        chunks={chunksInRow}
        enrichmentsByBlock={enrichmentsByBlock}
        chunkByBlockId={chunkByBlockId}
        selectedBlockId={selectedBlockId}
        activeChunkId={activeChunkId}
        parseChain={parseChain}
        onSelectBlock={selectBlock}
        onSelectChunk={selectChunk}
      />
    </section>
  );
}
