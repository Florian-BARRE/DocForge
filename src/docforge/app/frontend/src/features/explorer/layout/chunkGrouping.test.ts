// ====== Code Summary ======
// Unit tests for buildPageGroups' union-find: a chunk spanning page boundaries must pull ALL its
// pages into one group (across >2 pages, transitively), un-bridged pages stay solo, and a chunk that
// references a page absent from `pages` (an unseeded union-find key) must NOT hang the total `find`.

import { describe, expect, it } from "vitest";

import type { ChunkInfo, IRBlock, PageInfo } from "../../../api/explorer";
import { buildPageGroups } from "./chunkGrouping";

function page(n: number): PageInfo {
  return { page_number: n, width: null, height: null, is_scanned: false, language: null, render_blob_hash: null };
}

function block(id: string, pageNumber: number, order: number): IRBlock {
  return {
    id,
    block_type: "text",
    page: pageNumber,
    bbox: [0, 0, 1, 1],
    reading_order: order,
    column_index: 0,
    parent_id: null,
    level: null,
    text: null,
    is_boilerplate: false,
    language: null,
    confidence: null,
  } as IRBlock;
}

function chunk(id: string, blockIds: string[]): ChunkInfo {
  return {
    id,
    chunk_index: 0,
    text: "",
    token_count: 0,
    is_indexed: true,
    strategy: "fixed",
    parent_id: null,
    block_ids: blockIds,
    metadata: [],
    role: "body",
    enabled: true,
    heading_path: [],
    page: null,
  } as unknown as ChunkInfo;
}

describe("buildPageGroups", () => {
  it("keeps a boundary-spanning chunk's two pages in one group; unbridged pages stay solo", () => {
    const pages = [page(1), page(2), page(3)];
    const blocks = [block("a", 1, 0), block("b", 2, 1), block("c", 3, 2)];
    const chunks = [chunk("k", ["a", "b"])]; // spans pages 1↔2

    const groups = buildPageGroups(pages, blocks, chunks);

    expect(groups).toHaveLength(2);
    expect(groups[0].pages.map((p) => p.page_number)).toEqual([1, 2]);
    expect(groups[0].blocks.map((b) => b.id)).toEqual(["a", "b"]);
    expect(groups[1].pages.map((p) => p.page_number)).toEqual([3]);
  });

  it("unions ALL pages of a chunk that spans more than two pages (transitive chain)", () => {
    const pages = [page(1), page(2), page(3)];
    const blocks = [block("a", 1, 0), block("b", 2, 1), block("c", 3, 2)];
    const chunks = [chunk("k", ["a", "b", "c"])]; // spans 1↔2↔3

    const groups = buildPageGroups(pages, blocks, chunks);

    expect(groups).toHaveLength(1);
    expect(groups[0].pages.map((p) => p.page_number)).toEqual([1, 2, 3]);
  });

  it("does not hang when a chunk references a page absent from `pages` (unseeded find key)", () => {
    const pages = [page(1), page(2)];
    // Block "z" lives on page 9, which is NOT in `pages` — the old find() looped forever on it.
    const blocks = [block("a", 1, 0), block("z", 9, 1), block("b", 2, 2)];
    const chunks = [chunk("k", ["a", "z"]), chunk("j", ["b"])];

    const groups = buildPageGroups(pages, blocks, chunks);

    // Terminates and still buckets the real pages; page 9 has no PageInfo so it forms no group.
    const numbers = groups.flatMap((g) => g.pages.map((p) => p.page_number));
    expect(numbers).toContain(1);
    expect(numbers).toContain(2);
    expect(numbers).not.toContain(9);
  });
});
