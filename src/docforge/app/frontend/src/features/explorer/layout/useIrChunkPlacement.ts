// ====== Code Summary ======
// Measures the IR-blocks column and chunk cards (useLayoutEffect + a width-guarded ResizeObserver)
// and turns those rects into a Placement via the pure `computePlacement` (bandGeometry.ts). Owns
// every ref IrChunkGraph needs to attach to its DOM (container, both columns, per-block, per-chunk).

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { ChunkInfo, IRBlock } from "../../../api/explorer";
import { computePlacement, type Placement } from "./bandGeometry";
import type { ChunkMember } from "./chunkAssembly";

interface UseIrChunkPlacementParams {
  blocks: IRBlock[];
  chunks: ChunkInfo[];
  membersByChunk: Map<string, ChunkMember[]>;
  selectedBlockId: string | null;
  activeChunkId: string | null;
}

export function useIrChunkPlacement({ blocks, chunks, membersByChunk, selectedBlockId, activeChunkId }: UseIrChunkPlacementParams) {
  const containerRef = useRef<HTMLDivElement>(null);
  const midColRef = useRef<HTMLDivElement>(null);
  const chunkColRef = useRef<HTMLDivElement>(null);
  const irRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const chunkRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const lastWidth = useRef(0);
  const [tick, setTick] = useState(0);
  const [placement, setPlacement] = useState<Placement | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const mid = midColRef.current;
    const chunkCol = chunkColRef.current;
    if (!container || !mid || !chunkCol) return;

    const cRect = container.getBoundingClientRect();
    const midRightX = mid.getBoundingClientRect().right - cRect.left;
    const chunkLeftX = chunkCol.getBoundingClientRect().left - cRect.left;
    const midBottom = mid.getBoundingClientRect().bottom - cRect.top;

    const topY = new Map<string, number>();
    const botY = new Map<string, number>();
    for (const block of blocks) {
      const el = irRefs.current.get(block.id);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      topY.set(block.id, r.top - cRect.top);
      botY.set(block.id, r.bottom - cRect.top);
    }

    const chunkHeights = new Map<string, number>();
    for (const chunk of chunks) {
      chunkHeights.set(chunk.id, chunkRefs.current.get(chunk.id)?.getBoundingClientRect().height ?? 0);
    }

    setPlacement(
      computePlacement({ chunks, membersByChunk, midRightX, chunkLeftX, midBottom, topY, botY, chunkHeights, activeChunkId }),
    );
  }, [blocks, chunks, selectedBlockId, activeChunkId, tick, membersByChunk]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (Math.abs(width - lastWidth.current) > 0.5) {
        lastWidth.current = width;
        setTick((t) => t + 1);
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  return { containerRef, midColRef, chunkColRef, irRefs, chunkRefs, placement };
}
