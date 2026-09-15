// ====== Code Summary ======
// Render smoke-test for PageGroupRow covering the two idle-discoverability/legibility behaviors this
// pass introduced: (1) a chunk's grouping box carries an always-on, subtle "Cn" tag even without a
// click (the fix for "you can't see the chunks on the document" — chunkGrouping/PageBoxOverlay), and
// (2) a page whose blocks carry no real positional layout (the page-less html/md parser fallback,
// every block sharing the synthetic full-page bbox) shows the honest note instead of a stack of
// meaningless overlapping boxes. `lazy` image fetching never fires here (IntersectionObserver is a
// test-setup no-op), so this stays a pure DOM/jsdom smoke-test with no network.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ChunkInfo, IRBlock, PageInfo } from "../../../api/explorer";
import { DEFAULT_PAGE_ZOOM } from "./pageZoom";
import { PageGroupRow } from "./PageGroupRow";

function page(n: number): PageInfo {
  return { page_number: n, width: 800, height: 1000, is_scanned: false, language: "en", render_blob_hash: `hash-${n}` };
}

function block(id: string, pageNumber: number, order: number, bbox: number[]): IRBlock {
  return {
    id,
    block_type: "text",
    page: pageNumber,
    bbox,
    reading_order: order,
    parent_id: null,
    level: null,
    text: `block ${id}`,
    is_boilerplate: false,
    language: "en",
  };
}

function chunk(id: string, blockIds: string[]): ChunkInfo {
  return {
    id,
    chunk_index: 0,
    text: "chunk text",
    token_count: 3,
    is_indexed: true,
    strategy: "recursive",
    parent_id: null,
    block_ids: blockIds,
    metadata: [],
    role: "body",
    enabled: true,
    heading_path: [],
    page: 0,
  };
}

describe("PageGroupRow", () => {
  it("renders a positioned page's chunk box with an always-on idle 'Cn' tag (no click needed)", () => {
    const blocks = [block("b1", 0, 0, [0.1, 0.1, 0.5, 0.2]), block("b2", 0, 1, [0.1, 0.3, 0.5, 0.4])];
    const chunkByBlockId = new Map([
      ["b1", chunk("c1", ["b1", "b2"])],
      ["b2", chunk("c1", ["b1", "b2"])],
    ]);

    render(
      <PageGroupRow
        rowId="layout-pg-0"
        pages={[page(0)]}
        blocks={blocks}
        enrichmentsByBlock={new Map()}
        tablesByBlock={new Map()}
        chunkByBlockId={chunkByBlockId}
        parseChain={[]}
        pageZoom={DEFAULT_PAGE_ZOOM}
      />,
    );

    expect(screen.getByText("C0")).toBeInTheDocument();
  });

  it("shows the honest no-layout note for a page whose blocks all share the synthetic full-page bbox", () => {
    const blocks = [block("b1", 0, 0, [0, 0, 1, 1]), block("b2", 0, 1, [0, 0, 1, 1])];

    expect(() =>
      render(
        <PageGroupRow
          rowId="layout-pg-0"
          pages={[page(0)]}
          blocks={blocks}
          enrichmentsByBlock={new Map()}
          tablesByBlock={new Map()}
          chunkByBlockId={new Map()}
          parseChain={[]}
          pageZoom={DEFAULT_PAGE_ZOOM}
        />,
      ),
    ).not.toThrow();

    expect(screen.getByText(/No positional layout for this page/)).toBeInTheDocument();
  });
});
