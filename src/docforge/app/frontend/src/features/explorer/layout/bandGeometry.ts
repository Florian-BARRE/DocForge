// ====== Code Summary ======
// Pure geometry for the IR↔chunk Sankey ribbon: given measured rects (per-block top/bottom, per-
// chunk card height) it places every chunk card (centred on its members, de-overlapped downward)
// and builds one filled band per (chunk, member block) pair. No DOM/React here — kept separate
// from `useIrChunkPlacement` (the measuring hook) so the placement math is a plain, testable
// function.

import type { ChunkInfo } from "../../../api/explorer";
import { blockStyle } from "./blockColors";
import type { ChunkMember } from "./chunkAssembly";

const CARD_GAP = 16;

export interface Band {
  key: string;
  path: string;
  color: string;
  active: boolean;
}

export interface Placement {
  tops: Record<string, number>;
  bands: Band[];
  height: number;
}

interface ComputePlacementParams {
  chunks: ChunkInfo[];
  membersByChunk: Map<string, ChunkMember[]>;
  midRightX: number;
  chunkLeftX: number;
  midBottom: number;
  topY: Map<string, number>;
  botY: Map<string, number>;
  chunkHeights: Map<string, number>;
  activeChunkId: string | null;
}

export function computePlacement({
  chunks,
  membersByChunk,
  midRightX,
  chunkLeftX,
  midBottom,
  topY,
  botY,
  chunkHeights,
  activeChunkId,
}: ComputePlacementParams): Placement {
  const items = chunks
    .map((chunk) => {
      const members = (membersByChunk.get(chunk.id) ?? []).filter((m) => topY.has(m.block.id));
      const tops = members.map((m) => topY.get(m.block.id) as number);
      const bots = members.map((m) => botY.get(m.block.id) as number);
      const spanTop = tops.length ? Math.min(...tops) : 0;
      const spanBottom = bots.length ? Math.max(...bots) : 0;
      const chunkH = chunkHeights.get(chunk.id) ?? 0;
      return { chunk, members, spanTop, spanBottom, centre: (spanTop + spanBottom) / 2, chunkH };
    })
    .sort((a, b) => a.centre - b.centre);

  const tops: Record<string, number> = {};
  let prevBottom = 0;
  for (const item of items) {
    const placed = Math.max(item.centre - item.chunkH / 2, prevBottom + CARD_GAP, 0);
    tops[item.chunk.id] = placed;
    prevBottom = placed + item.chunkH;
  }

  // A WIDE ribbon per chunk, split into one filled sub-band per member block (coloured by its IR
  // type): each band flows from the block's own vertical extent on the left into an equal slice of
  // the card's left edge on the right, so the stacked bands read as a multi-coloured Sankey flow.
  const bands: Band[] = [];
  const mx = midRightX + (chunkLeftX - midRightX) * 0.5;
  const CARD_PAD = 4;
  for (const item of items) {
    const active = activeChunkId === item.chunk.id;
    const cardTop = tops[item.chunk.id] + CARD_PAD;
    const usableH = Math.max(item.chunkH - CARD_PAD * 2, 0);
    const n = item.members.length;
    item.members.forEach((member, i) => {
      const lt = topY.get(member.block.id) as number;
      const lb = botY.get(member.block.id) as number;
      const rTop = cardTop + (i / n) * usableH;
      const rBot = cardTop + ((i + 1) / n) * usableH;
      bands.push({
        key: `${item.chunk.id}:${member.block.id}`,
        path:
          `M ${midRightX} ${lt} ` +
          `C ${mx} ${lt} ${mx} ${rTop} ${chunkLeftX} ${rTop} ` +
          `L ${chunkLeftX} ${rBot} ` +
          `C ${mx} ${rBot} ${mx} ${lb} ${midRightX} ${lb} Z`,
        color: blockStyle(member.block.block_type).color,
        active,
      });
    });
  }

  return { tops, bands, height: Math.max(midBottom, prevBottom, 0) };
}
