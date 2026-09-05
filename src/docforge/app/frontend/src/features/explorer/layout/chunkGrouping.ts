// ====== Code Summary ======
// Pure helpers that join the IR (blocks) to the retrieval chunks for the Layout view: which chunk a
// block was folded into, and the union bounding box of a chunk's blocks (the "grouping" box drawn as
// one solid outline around its members on the page). No React, no theme — just the block↔chunk
// geometry the three columns (page overlay, IR list, chunk list) all consume.

import type { ChunkInfo, IRBlock, PageInfo } from "../../../api/explorer";

/** A run of consecutive pages joined because a chunk spans across their boundary, shown as one row. */
export interface PageGroup {
  pages: PageInfo[];
  blocks: IRBlock[];
}

/**
 * Build a block-id → chunk lookup from a document's chunks.
 *
 * A chunk lists the block ids it was composed from; we invert that into per-block membership. A block
 * is normally in at most one chunk — if it appears in several, the first chunk (lowest index, since
 * chunks arrive index-ordered) wins so the mapping stays 1:1.
 */
export function buildChunkByBlockId(chunks: ChunkInfo[]): Map<string, ChunkInfo> {
  const map = new Map<string, ChunkInfo>();
  for (const chunk of chunks) {
    for (const blockId of chunk.block_ids) {
      if (!map.has(blockId)) map.set(blockId, chunk);
    }
  }
  return map;
}

/**
 * Group pages so that any chunk spanning a page boundary keeps BOTH its pages in the same row.
 *
 * A chunk whose blocks fall on pages N and N+1 must be inspectable as one continuous unit — the end
 * of page N flowing into the start of page N+1 — so we union every pair of pages a chunk touches
 * (transitively) and emit one group per connected run. Pages no chunk bridges stay solo. Each group's
 * blocks are returned in global reading order, so a spanning chunk's members are contiguous.
 *
 * Args:
 *   pages: the document's pages.
 *   blocks: every IR block (carries its page + reading order).
 *   chunks: the retrieval chunks (their block_ids decide which pages are bridged).
 *
 * Returns: page groups, ordered by first page; single-page groups for the common case.
 */
export function buildPageGroups(pages: PageInfo[], blocks: IRBlock[], chunks: ChunkInfo[]): PageGroup[] {
  // 1. Union-find over page numbers. `find` is TOTAL: an unseeded key seeds itself as its own root
  //    and returns immediately — never spinning (the old `parent.get(root) ?? root` looped forever on
  //    a key absent from the map, since `undefined ?? root` re-yields the same non-root key).
  const parent = new Map<number, number>();
  const find = (n: number): number => {
    if (parent.get(n) === undefined) {
      parent.set(n, n);
      return n;
    }
    let root = n;
    while (parent.get(root) !== root) root = parent.get(root)!;
    return root;
  };
  const union = (a: number, b: number) => {
    parent.set(find(a), find(b));
  };
  for (const page of pages) parent.set(page.page_number, page.page_number);

  // 2. Bridge every page a single chunk touches into one component. Chaining consecutive touched
  //    pages (not just anchoring the rest to the first) keeps the intent obvious and connects them
  //    all transitively; `find` seeds any page a block references that is not in `pages`.
  const pageOfBlock = new Map<string, number>();
  for (const block of blocks) pageOfBlock.set(block.id, block.page);
  for (const chunk of chunks) {
    const chunkPages = chunk.block_ids.map((id) => pageOfBlock.get(id)).filter((n): n is number => n != null);
    for (let i = 1; i < chunkPages.length; i += 1) {
      union(chunkPages[i - 1], chunkPages[i]);
    }
  }

  // 3. Bucket pages by root, then assemble each group's pages + reading-ordered blocks.
  const buckets = new Map<number, PageInfo[]>();
  for (const page of pages) {
    const root = find(page.page_number);
    (buckets.get(root) ?? buckets.set(root, []).get(root)!).push(page);
  }
  const groups: PageGroup[] = [];
  for (const groupPages of buckets.values()) {
    groupPages.sort((a, b) => a.page_number - b.page_number);
    const pageNumbers = new Set(groupPages.map((p) => p.page_number));
    const groupBlocks = blocks
      .filter((b) => pageNumbers.has(b.page))
      .sort((a, b) => a.reading_order - b.reading_order);
    if (groupBlocks.length > 0) groups.push({ pages: groupPages, blocks: groupBlocks });
  }
  return groups.sort((a, b) => a.pages[0].page_number - b.pages[0].page_number);
}

/**
 * Union bounding box of several normalized [x0, y0, x1, y1] boxes, padded outward.
 *
 * Used to draw one larger box around all of a chunk's blocks on a page. The small pad keeps the
 * grouping box just outside its members so their own boxes stay readable inside it.
 */
export function unionBbox(bboxes: number[][], pad = 0.004): number[] {
  const x0 = Math.min(...bboxes.map((b) => b[0])) - pad;
  const y0 = Math.min(...bboxes.map((b) => b[1])) - pad;
  const x1 = Math.max(...bboxes.map((b) => b[2])) + pad;
  const y1 = Math.max(...bboxes.map((b) => b[3])) + pad;
  return [x0, y0, x1, y1];
}
