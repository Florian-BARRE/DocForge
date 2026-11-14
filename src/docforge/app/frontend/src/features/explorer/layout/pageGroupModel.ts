// ====== Code Summary ======
// Pure model of one Layout row (PageGroupRow / usePageGroupRow): the shared block/chunk selection,
// the row's reading-order index and chunk list, the pages with no real layout, and the overlay boxes
// drawn on each page. No React — the hook memoises these, the view renders them.

import type { ChunkInfo, IRBlock, PageInfo } from "../../../api/explorer";
import type { OverlayBox } from "../../../components/PageBoxOverlay";
import { theme } from "../../../theme";
import { blockStyle } from "./blockColors";
import { pageBlocksLackLayout, unionBbox } from "./chunkGrouping";

export type Selection = { kind: "block" | "chunk"; id: string };

// The page render is the important element — readable, roomy, but capped well short of hogging the
// row so the IR/chunk lanes always have real room beside it (feedback: the previous 620px max left
// too little for the other two lanes at normal viewport widths).
export const PAGE_COLUMN_MIN_PX = 360;
export const PAGE_COLUMN_MAX_PX = 480;
// A sane pre-measurement default (before the column's ResizeObserver reports in), within the band
// above — avoids a jarring first-paint jump once the real measurement lands.
export const DEFAULT_COLUMN_WIDTH_PX = 440;
// The IR-blocks lane is a SUPPORTING lane, not the main subject — capped narrower than before and
// pulled close to the page (see the row's `gap`) so the extracted IR reads as sitting right
// next to its source image, per feedback.
export const IR_COLUMN_WIDTH_PX = 300;
// The chunk lane, on the right, gets a comfortable, readable width.
export const CHUNK_COLUMN_WIDTH_PX = 384;

/** Click on a block/chunk: select it, or clear the selection when it already is the selected one. */
export function toggleSelection(prev: Selection | null, kind: Selection["kind"], id: string): Selection | null {
  return prev?.kind === kind && prev.id === id ? null : { kind, id };
}

/** The chunk that is "active": the selected chunk, else the chunk of the selected block. */
export function activeChunkIdOf(
  selected: Selection | null,
  chunkByBlockId: Map<string, ChunkInfo>,
): string | null {
  const selectedBlockId = selected?.kind === "block" ? selected.id : null;
  if (selected?.kind === "chunk") return selected.id;
  return selectedBlockId ? chunkByBlockId.get(selectedBlockId)?.id ?? null : null;
}

/** Each block's position in the row's continuous reading order (shared by page badge and card). */
export function indexByBlockIdOf(blocks: IRBlock[]): Map<string, number> {
  const map = new Map<string, number>();
  blocks.forEach((block, index) => map.set(block.id, index));
  return map;
}

/** The chunks present in the row, in first-appearance order (drives the right column). */
export function chunksInRowOf(blocks: IRBlock[], chunkByBlockId: Map<string, ChunkInfo>): ChunkInfo[] {
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
}

/**
 * Pages whose blocks carry no real positional layout (a page-less html/md parse — see
 * chunkGrouping.ts): they would only draw indistinguishable full-page boxes on top of each other, so
 * the overlay boxes are withheld there and the view shows an honest note instead.
 */
export function noLayoutPagesOf(pages: PageInfo[], blocks: IRBlock[]): Set<number> {
  const set = new Set<number>();
  for (const page of pages) {
    const pageBlocks = blocks.filter((b) => b.page === page.page_number);
    if (pageBlocksLackLayout(pageBlocks)) set.add(page.page_number);
  }
  return set;
}

/** Nudge a block box outward so its border floats just OFF the glyphs instead of cutting through them. */
function padOut(bb: number[], d = 0.005): number[] {
  return [bb[0] - d, bb[1] - d, bb[2] + d, bb[3] + d];
}

export interface BoxesInput {
  pages: PageInfo[];
  blocks: IRBlock[];
  chunkByBlockId: Map<string, ChunkInfo>;
  indexByBlockId: Map<string, number>;
  noLayoutPages: Set<number>;
  activeChunkId: string | null;
  selectedBlockId: string | null;
  hasSelection: boolean;
  onSelectBlock: (id: string) => void;
  onSelectChunk: (id: string) => void;
}

/**
 * The overlay boxes for every page in the row. COLOUR = IR TYPE (same hue as the block's card + its
 * segment in the chunk — one colour means one thing everywhere); body Text stays neutral so a page
 * isn't a rainbow, only the notable types pop. CHUNK GROUPING is a neutral dashed outline that
 * carries an always-on, subtle "Cn" tag (PageBoxOverlay) even at idle — so a document reads as
 * chunked without a click — and a spanning chunk draws it on both pages. The forge accent is
 * reserved for the active one; everything outside the current selection dims.
 */
export function buildBoxesByPage(input: BoxesInput): Map<number, OverlayBox[]> {
  const {
    pages, blocks, chunkByBlockId, indexByBlockId, noLayoutPages,
    activeChunkId, selectedBlockId, hasSelection, onSelectBlock, onSelectChunk,
  } = input;
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
        onSelect: () => onSelectChunk(chunk.id),
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
        onSelect: () => onSelectBlock(block.id),
        selectLabel: `Block ${index + 1}, ${blockStyle(block.block_type).label}`,
      };
    });

    map.set(pageNumber, [...groupBoxes, ...blockBoxes]);
  }
  return map;
}
