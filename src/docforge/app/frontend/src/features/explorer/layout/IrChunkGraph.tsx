// ====== Code Summary ======
// The connected flow of one row: IR BLOCKS (middle) → CHUNKS (right). Each chunk card sits centred on
// its member blocks and is tied to them by a WIDE Sankey ribbon that is SUBDIVIDED into stacked sub-
// bands — one filled band PER member block, coloured by that block's IR TYPE (a heading band is red, a
// text band grey, …). Each band flows from the block's own vertical extent (left) into its slice of
// the card's edge (right), so the multi-coloured ribbon shows exactly what — and in what proportion —
// flowed into the chunk. The chunk card carries all the provenance (no separate column). Selection pops
// a chunk's bands + card to full colour; the rest dim.
//
// This component only wires the three pieces together: `useIrChunkPlacement` measures the DOM and
// produces a Placement (bandGeometry.ts has the pure geometry), `IrBlocksColumn` renders the middle
// column, `ChunkPlacementColumn` the right one.

import { useMemo } from "react";

import type { ChunkInfo, IRBlock, IREnrichment, IRTable } from "../../../api/explorer";
import type { ChunkMember } from "./chunkAssembly";
import { ChunkPlacementColumn } from "./ChunkPlacementColumn";
import { IrBlocksColumn } from "./IrBlocksColumn";
import { useIrChunkPlacement } from "./useIrChunkPlacement";

const CONNECTOR = 48; // px — the strand-bundle zone between the two lanes (tight; ribbons still read)

interface IrChunkGraphProps {
  blocks: IRBlock[];
  chunks: ChunkInfo[];
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  tablesByBlock: Map<string, IRTable>;
  chunkByBlockId: Map<string, ChunkInfo>;
  selectedBlockId: string | null;
  activeChunkId: string | null;
  parseChain: { kind: string; status: string }[];
  /** The IR-blocks lane's own width (px) — a fixed, capped value (not "whatever space is left") so
   *  it stays a compact SUPPORTING lane beside the page even on a wide viewport. */
  irWidth: number;
  /** The chunk lane's own width (px) — comfortable/readable, on the far right. */
  chunkWidth: number;
  onSelectBlock: (blockId: string) => void;
  onSelectChunk: (chunkId: string) => void;
}

export function IrChunkGraph({
  blocks,
  chunks,
  enrichmentsByBlock,
  tablesByBlock,
  chunkByBlockId,
  selectedBlockId,
  activeChunkId,
  parseChain,
  irWidth,
  chunkWidth,
  onSelectBlock,
  onSelectChunk,
}: IrChunkGraphProps) {
  const membersByChunk = useMemo(() => {
    const map = new Map<string, ChunkMember[]>();
    blocks.forEach((block, index) => {
      const chunk = chunkByBlockId.get(block.id);
      if (!chunk) return;
      const arr = map.get(chunk.id) ?? [];
      arr.push({ block, index });
      map.set(chunk.id, arr);
    });
    return map;
  }, [blocks, chunkByBlockId]);

  const { containerRef, midColRef, chunkColRef, irRefs, chunkRefs, placement } = useIrChunkPlacement({
    blocks,
    chunks,
    membersByChunk,
    selectedBlockId,
    activeChunkId,
  });

  // Draw inactive bands first so an active chunk's coloured ribbon always sits on top.
  const orderedBands = placement ? [...placement.bands].sort((a, b) => Number(a.active) - Number(b.active)) : [];

  // FIXED total width (never `minWidth`/1fr-stretch) — this is what keeps the IR lane a compact,
  // capped supporting lane instead of ballooning to fill whatever space a wide viewport's grid track
  // leaves it. Below that width (a narrow viewport/grid track) this wrapper scrolls HORIZONTALLY
  // WITHIN ITSELF, rather than overflowing into the page body (which must never scroll sideways) or
  // stacking the lanes (rejected — it hid the graph entirely below a tall page render).
  const totalWidth = irWidth + CONNECTOR + chunkWidth;
  return (
    <div style={{ overflowX: "auto" }}>
      <div ref={containerRef} style={{ position: "relative", width: totalWidth, minHeight: placement?.height ?? undefined }}>
        <svg
          style={{ position: "absolute", inset: 0, width: "100%", height: placement?.height ?? 0, pointerEvents: "none", overflow: "visible", zIndex: 0 }}
          aria-hidden="true"
        >
          {orderedBands.map((band) => (
            <path
              key={band.key}
              d={band.path}
              fill={band.color}
              stroke={band.color}
              strokeWidth={0.5}
              style={{
                fillOpacity: band.active ? 0.5 : 0.13,
                strokeOpacity: band.active ? 0.55 : 0.14,
                transition: "fill-opacity .15s ease, stroke-opacity .15s ease",
              }}
            />
          ))}
        </svg>

        <IrBlocksColumn
          midColRef={midColRef}
          irRefs={irRefs}
          blocks={blocks}
          chunkByBlockId={chunkByBlockId}
          enrichmentsByBlock={enrichmentsByBlock}
          selectedBlockId={selectedBlockId}
          activeChunkId={activeChunkId}
          parseChain={parseChain}
          marginRight={CONNECTOR + chunkWidth}
          onSelectBlock={onSelectBlock}
        />

        <ChunkPlacementColumn
          chunkColRef={chunkColRef}
          chunkRefs={chunkRefs}
          chunks={chunks}
          membersByChunk={membersByChunk}
          enrichmentsByBlock={enrichmentsByBlock}
          tablesByBlock={tablesByBlock}
          placement={placement}
          selectedBlockId={selectedBlockId}
          activeChunkId={activeChunkId}
          width={chunkWidth}
          onSelectChunk={onSelectChunk}
        />
      </div>
    </div>
  );
}
