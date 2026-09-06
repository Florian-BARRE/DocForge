// ====== Code Summary ======
// Unit tests for segmentChunkText's provenance attribution — the MOYENNE audit bug: a TABLE block's
// rendered markdown grid must map to the TABLE block (not fall through as unattributed glue), and a
// CARRIED heading that the chunker dropped as a duplicate of its own section's first line must not
// steal that line's attribution away from the paragraph it actually belongs to.

import { describe, expect, it } from "vitest";

import type { ChunkInfo, IRBlock, IREnrichment, IRTable } from "../../../api/explorer";
import { chunkProvenance, segmentChunkText, type ChunkMember } from "./chunkAssembly";

function block(id: string, blockType: string, text: string | null, order: number): IRBlock {
  return {
    id,
    block_type: blockType,
    page: 1,
    bbox: [0, 0, 1, 1],
    reading_order: order,
    parent_id: null,
    level: null,
    text,
    is_boilerplate: false,
    language: null,
  };
}

function table(blockId: string, cells: string[][], hasHeader: boolean): IRTable {
  return {
    block_id: blockId,
    n_rows: cells.length,
    n_cols: Math.max(...cells.map((row) => row.length)),
    has_header: hasHeader,
    cells,
    linearized_md: null,
  };
}

const NO_ENRICHMENTS = new Map<string, IREnrichment[]>();

describe("segmentChunkText", () => {
  it("maps a TABLE block's rendered markdown grid to the table block, not to glue", () => {
    const tableBlock = block("t1", "table", null, 0);
    const rendered = "| Name | Score |\n| --- | --- |\n| Alice | 92 |";
    const members: ChunkMember[] = [{ block: tableBlock, index: 0 }];
    const tablesByBlock = new Map([["t1", table("t1", [["Name", "Score"], ["Alice", "92"]], true)]]);

    const segments = segmentChunkText(rendered, members, NO_ENRICHMENTS, tablesByBlock);

    expect(segments).toEqual([{ text: rendered, blockType: "table", blockIndex: 0, added: false }]);
  });

  it("keeps a folded caption on the CAPTION block and the grid on the TABLE block (no cross-bleed)", () => {
    const captionBlock = block("cap1", "caption", "Table 1: scores", 0);
    const tableBlock = block("t1", "table", null, 1);
    const rendered = "| Name | Score |\n| --- | --- |\n| Alice | 92 |";
    const chunkText = `Table 1: scores\n${rendered}`;
    const members: ChunkMember[] = [
      { block: captionBlock, index: 0 },
      { block: tableBlock, index: 1 },
    ];
    const tablesByBlock = new Map([["t1", table("t1", [["Name", "Score"], ["Alice", "92"]], true)]]);

    const segments = segmentChunkText(chunkText, members, NO_ENRICHMENTS, tablesByBlock);

    const tableSegment = segments.find((s) => s.blockType === "table");
    expect(tableSegment).toEqual({ text: rendered, blockType: "table", blockIndex: 1, added: false });
    const captionSegment = segments.find((s) => s.blockType === "caption");
    expect(captionSegment).toEqual({ text: "Table 1: scores", blockType: "caption", blockIndex: 0, added: false });
  });

  it("does not steal a duplicated carried heading's text from the following paragraph", () => {
    // Mirrors BaseChunkerNode.__prepend_heading's duplicate branch: the heading's title equals the
    // paragraph's own first line, so the chunker drops the heading text entirely — chunk.text is the
    // paragraph's text, UNCHANGED — even though the heading's block id still travels for provenance.
    const headingBlock = block("h1", "heading", "Overview", 0);
    const paragraphBlock = block("p1", "paragraph", "Overview\nThis section explains the overview details.", 1);
    const chunkText = "Overview\nThis section explains the overview details.";
    const members: ChunkMember[] = [
      { block: headingBlock, index: 0 },
      { block: paragraphBlock, index: 1 },
    ];

    const segments = segmentChunkText(chunkText, members, NO_ENRICHMENTS);

    // The heading contributes no segment of its own (it added no text)...
    expect(segments.some((s) => s.blockType === "heading")).toBe(false);
    // ...and the WHOLE text — including its leading "Overview" line — is attributed to the paragraph,
    // not split off into an unattributed leading "added" glue segment.
    expect(segments).toEqual([{ text: chunkText, blockType: "paragraph", blockIndex: 1, added: false }]);
  });

  it("still attributes a NON-duplicate carried heading to its own heading block", () => {
    // Mirrors the non-duplicate __prepend_heading branch: `f"{heading.text}\n\n{passage.text}"`.
    const headingBlock = block("h1", "heading", "Chapter 2", 0);
    const paragraphBlock = block("p1", "paragraph", "Body content of chapter two.", 1);
    const chunkText = "Chapter 2\n\nBody content of chapter two.";
    const members: ChunkMember[] = [
      { block: headingBlock, index: 0 },
      { block: paragraphBlock, index: 1 },
    ];

    const segments = segmentChunkText(chunkText, members, NO_ENRICHMENTS);

    expect(segments).toEqual([
      { text: "Chapter 2", blockType: "heading", blockIndex: 0, added: false },
      { text: "\n\n", added: true },
      { text: "Body content of chapter two.", blockType: "paragraph", blockIndex: 1, added: false },
    ]);
  });
});

describe("chunkProvenance — degraded payload guard", () => {
  // Regression test for the P0 Layout-tab crash: a chunk row whose `heading_path`/`metadata` arrays
  // are absent (a stale/partial payload, not the normal `[]` the backend always sends) must degrade
  // to "nothing added" instead of throwing `Cannot read properties of undefined (reading 'length')`.
  it("does not throw when heading_path and metadata are missing from the chunk payload", () => {
    const degradedChunk = {
      id: "c1",
      chunk_index: 0,
      text: "chunk text",
      token_count: 2,
      is_indexed: true,
      strategy: "recursive",
      parent_id: null,
      block_ids: [],
      role: "body",
      enabled: true,
      page: null,
      // heading_path and metadata deliberately OMITTED — the exact repro shape.
    } as unknown as ChunkInfo;

    expect(() => chunkProvenance(degradedChunk, [], new Map())).not.toThrow();
    expect(chunkProvenance(degradedChunk, [], new Map())).toEqual([]);
  });
});
