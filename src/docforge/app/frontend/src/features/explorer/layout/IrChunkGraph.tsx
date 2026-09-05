// ====== Code Summary ======
// The connected flow of one row: IR BLOCKS (middle) → CHUNKS (right). Each chunk card sits centred on
// its member blocks and is tied to them by a WIDE Sankey ribbon that is SUBDIVIDED into stacked sub-
// bands — one filled band PER member block, coloured by that block's IR TYPE (a heading band is red, a
// text band grey, …). Each band flows from the block's own vertical extent (left) into its slice of the
// card's edge (right), so the multi-coloured ribbon shows exactly what — and in what proportion —
// flowed into the chunk. The chunk card carries all the provenance (no separate column). Selection pops
// a chunk's bands + card to full colour; the rest dim.
//
// Layout is measured (useLayoutEffect + width-guarded ResizeObserver): chunk cards are centred on their
// members with a downward de-overlap pass; band geometry is derived from the measured rects.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { ChunkInfo, IRBlock, IREnrichment, IRTable } from "../../../api/explorer";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { blockStyle } from "./blockColors";
import { ChunkColumnCard } from "./ChunkColumnCard";
import type { ChunkMember } from "./chunkAssembly";
import { ReadingOrderEntry } from "./ReadingOrderEntry";

const CHUNK_WIDTH = 384;
const CONNECTOR = 92; // px — the strand-bundle zone between the two columns
const CARD_GAP = 16;

interface Band {
  key: string;
  path: string;
  color: string;
  active: boolean;
}

interface Placement {
  tops: Record<string, number>;
  bands: Band[];
  height: number;
}

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
  const containerRef = useRef<HTMLDivElement>(null);
  const midColRef = useRef<HTMLDivElement>(null);
  const chunkColRef = useRef<HTMLDivElement>(null);
  const irRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const chunkRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const lastWidth = useRef(0);
  const [tick, setTick] = useState(0);
  const [placement, setPlacement] = useState<Placement | null>(null);

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

    const items = chunks
      .map((chunk) => {
        const members = (membersByChunk.get(chunk.id) ?? []).filter((m) => topY.has(m.block.id));
        const tops = members.map((m) => topY.get(m.block.id) as number);
        const bots = members.map((m) => botY.get(m.block.id) as number);
        const spanTop = tops.length ? Math.min(...tops) : 0;
        const spanBottom = bots.length ? Math.max(...bots) : 0;
        const chunkH = chunkRefs.current.get(chunk.id)?.getBoundingClientRect().height ?? 0;
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

    setPlacement({ tops, bands, height: Math.max(midBottom, prevBottom, 0) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

        {/* MIDDLE — every IR block in reading order (type-coloured spine + extraction provenance). */}
        <div ref={midColRef} style={{ position: "relative", zIndex: 1, marginRight: CONNECTOR + CHUNK_WIDTH, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          <div style={{ fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, color: theme.color.dim, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            IR blocks
          </div>
          {blocks.map((block, index) => {
            const chunk = chunkByBlockId.get(block.id) ?? null;
            const selected = selectedBlockId === block.id;
            const related = !selected && chunk != null && chunk.id === activeChunkId;
            const prev = blocks[index - 1];
            const showDivider = prev && prev.page !== block.page;
            return (
              <div key={block.id} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
                {showDivider && (
                  <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, margin: `${theme.space.xs}px 0` }} aria-hidden="true">
                    <div style={{ flex: 1, height: 1, background: theme.color.line }} />
                    <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute, whiteSpace: "nowrap" }}>
                      page {displayPage(prev.page)} → {displayPage(block.page)}
                    </span>
                    <div style={{ flex: 1, height: 1, background: theme.color.line }} />
                  </div>
                )}
                <div
                  ref={(el) => {
                    if (el) irRefs.current.set(block.id, el);
                    else irRefs.current.delete(block.id);
                  }}
                >
                  <ReadingOrderEntry
                    block={block}
                    index={index}
                    enrichments={enrichmentsByBlock.get(block.id) ?? []}
                    selected={selected}
                    related={related}
                    parseChain={parseChain}
                    onSelect={() => onSelectBlock(block.id)}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* CHUNKS — centred on their members; each card carries its full provenance. */}
        <div ref={chunkColRef} style={{ position: "absolute", top: 0, right: 0, width: CHUNK_WIDTH, zIndex: 1 }}>
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
      </div>
    </div>
  );
}
