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

const CHUNK_WIDTH = 384;
const CONNECTOR = 92; // px — the strand-bundle zone between the two columns

interface IrChunkGraphProps {
  blocks: IRBlock[];
  chunks: ChunkInfo[];
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  tablesByBlock: Map<string, IRTable>;
  chunkByBlockId: Map<string, ChunkInfo>;
  selectedBlockId: string | null;
  activeChunkId: string | null;
  parseChain: { kind: string; status: string }[];
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

  // The two columns reserve a fixed width (CHUNK_WIDTH + CONNECTOR) that can exceed a narrow
  // viewport — this wrapper scrolls HORIZONTALLY WITHIN ITSELF when that happens, rather than
  // overflowing into the page body (which must never scroll sideways).
  return (
    <div style={{ overflowX: "auto" }}>
      <div ref={containerRef} style={{ position: "relative", minWidth: CONNECTOR + CHUNK_WIDTH + 240, minHeight: placement?.height ?? undefined }}>
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
          marginRight={CONNECTOR + CHUNK_WIDTH}
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
          width={CHUNK_WIDTH}
          onSelectChunk={onSelectChunk}
        />
      </div>
    </div>
  );
}
