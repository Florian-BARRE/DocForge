// ====== Code Summary ======
// The IR-blocks column of the Sankey graph (middle) — every block in reading order, with page-break
// dividers between them, each wrapped in the ref `useIrChunkPlacement` needs to measure its rect.

import type { MutableRefObject, RefObject } from "react";

import type { ChunkInfo, IRBlock, IREnrichment } from "../../../api/explorer";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { ReadingOrderEntry } from "./ReadingOrderEntry";

interface IrBlocksColumnProps {
  midColRef: RefObject<HTMLDivElement>;
  irRefs: MutableRefObject<Map<string, HTMLDivElement>>;
  blocks: IRBlock[];
  chunkByBlockId: Map<string, ChunkInfo>;
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  selectedBlockId: string | null;
  activeChunkId: string | null;
  parseChain: { kind: string; status: string }[];
  marginRight: number;
  onSelectBlock: (blockId: string) => void;
}

export function IrBlocksColumn({
  midColRef,
  irRefs,
  blocks,
  chunkByBlockId,
  enrichmentsByBlock,
  selectedBlockId,
  activeChunkId,
  parseChain,
  marginRight,
  onSelectBlock,
}: IrBlocksColumnProps) {
  return (
    <div ref={midColRef} style={{ position: "relative", zIndex: 1, marginRight, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
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
  );
}
