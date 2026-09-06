// ====== Code Summary ======
// The chunk-cards column of the Sankey graph (right) — each card absolutely positioned per
// `Placement.tops` so it sits centred on its member blocks; `useIrChunkPlacement` measures these
// same rects through `chunkRefs` to compute that layout.

import type { MutableRefObject, RefObject } from "react";

import type { ChunkInfo, IREnrichment, IRTable } from "../../../api/explorer";
import type { Placement } from "./bandGeometry";
import type { ChunkMember } from "./chunkAssembly";
import { ChunkColumnCard } from "./ChunkColumnCard";

interface ChunkPlacementColumnProps {
  chunkColRef: RefObject<HTMLDivElement>;
  chunkRefs: MutableRefObject<Map<string, HTMLDivElement>>;
  chunks: ChunkInfo[];
  membersByChunk: Map<string, ChunkMember[]>;
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  tablesByBlock: Map<string, IRTable>;
  placement: Placement | null;
  selectedBlockId: string | null;
  activeChunkId: string | null;
  width: number;
  onSelectChunk: (chunkId: string) => void;
}

export function ChunkPlacementColumn({
  chunkColRef,
  chunkRefs,
  chunks,
  membersByChunk,
  enrichmentsByBlock,
  tablesByBlock,
  placement,
  selectedBlockId,
  activeChunkId,
  width,
  onSelectChunk,
}: ChunkPlacementColumnProps) {
  return (
    <div ref={chunkColRef} style={{ position: "absolute", top: 0, right: 0, width, zIndex: 1 }}>
      {chunks.map((chunk) => {
        const members = membersByChunk.get(chunk.id) ?? [];
        const selBlockIndex =
          selectedBlockId != null ? members.find((m) => m.block.id === selectedBlockId)?.index ?? null : null;
        return (
          <div
            key={chunk.id}
            ref={(el) => {
              if (el) chunkRefs.current.set(chunk.id, el);
              else chunkRefs.current.delete(chunk.id);
            }}
            style={{ position: "absolute", top: placement?.tops[chunk.id] ?? 0, left: 0, right: 0, opacity: placement ? 1 : 0, transition: "top .18s ease, opacity .18s ease" }}
          >
            <ChunkColumnCard
              chunk={chunk}
              members={members}
              enrichmentsByBlock={enrichmentsByBlock}
              tablesByBlock={tablesByBlock}
              selected={activeChunkId === chunk.id}
              selectedBlockIndex={selBlockIndex}
              onSelect={() => onSelectChunk(chunk.id)}
            />
          </div>
        );
      })}
    </div>
  );
}
