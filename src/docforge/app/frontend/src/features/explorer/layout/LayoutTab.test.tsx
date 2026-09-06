// ====== Code Summary ======
// Render smoke-test for LayoutTab across its four top-level branches — error, loading, empty (no
// located blocks) and loaded — plus the non-blocking chunks-error banner on the loaded branch. It
// guards the exact class of bug the frontend render-smoke gate exists for: LayoutTab runs FIVE
// useMemo hooks (enrichments, chunk map, tables, page groups, parse chain) that MUST stay above its
// conditional returns — a hook slipping below one would pass `tsc`/`build` yet throw at runtime the
// moment the component renders past `loading`. Asserting each branch mounts without throwing is that
// gate. The heavy leaf children (PageGroupRow's SVG flow graph + image overlays, the scrubber, the
// legend) are stubbed so the test stays deterministic in jsdom and focused on LayoutTab's own logic;
// buildPageGroups/buildChunkByBlockId still run for real, so the loaded branch's grouping is exercised.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChunkInfo, DocumentIR, DocumentProvenance, IRBlock, PageInfo } from "../../../api/explorer";
import { LayoutTab } from "./LayoutTab";

// Stub the heavy children — LayoutTab's own hooks/branches are what this smoke-test guards; each stub
// renders a marker so the loaded branch is observable without a deep SVG/image render.
vi.mock("./PageGroupRow", () => ({ PageGroupRow: () => <div data-testid="page-group-row" /> }));
vi.mock("./PageScrubber", () => ({ PageScrubber: () => <div data-testid="page-scrubber" /> }));
vi.mock("./BlockTypeLegend", () => ({ BlockTypeLegend: () => <div data-testid="block-legend" /> }));

function page(n: number): PageInfo {
  return { page_number: n, width: 800, height: 1000, is_scanned: false, language: "en", render_blob_hash: `hash-${n}` };
}

function block(id: string, pageNumber: number, order: number): IRBlock {
  return {
    id,
    block_type: "text",
    page: pageNumber,
    bbox: [0.1, 0.1, 0.9, 0.2],
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

const loadedIR: DocumentIR = {
  blocks: [block("b1", 0, 0), block("b2", 0, 1)],
  tables: [],
  figures: [],
  enrichments: [
    { id: "e1", block_id: "b1", kind: "ocr", text: "ocr text", data: null, status: "ok" },
  ],
};
const loadedPages = [page(0)];
const loadedChunks = [chunk("c1", ["b1", "b2"])];
const loadedProvenance: DocumentProvenance = {
  document_id: "doc-1",
  pipeline_version: "v1",
  job_id: "job-1",
  available: true,
  stages: [
    { stage: "parse", status: "success", node_kind: "docling", started_at: null, finished_at: null, detail: null, prompt_tokens: null, completion_tokens: null, cost_usd: null },
  ],
};

const noop = () => {};

describe("LayoutTab — branch render smoke-tests", () => {
  it("renders the error branch without throwing", () => {
    expect(() =>
      render(
        <LayoutTab
          ir={null} pages={null} chunks={null} provenance={null}
          error="boom" chunksError={null} onRetry={noop} onRetryChunks={noop}
        />,
      ),
    ).not.toThrow();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders the loading branch while IR/pages are still null", () => {
    render(
      <LayoutTab
        ir={null} pages={loadedPages} chunks={null} provenance={null}
        error={null} chunksError={null} onRetry={noop} onRetryChunks={noop}
      />,
    );
    expect(screen.getByText("loading layout…")).toBeInTheDocument();
  });

  it("renders the empty branch when the IR has no located blocks", () => {
    render(
      <LayoutTab
        ir={{ blocks: [], tables: [], figures: [], enrichments: [] }}
        pages={loadedPages} chunks={[]} provenance={null}
        error={null} chunksError={null} onRetry={noop} onRetryChunks={noop}
      />,
    );
    expect(screen.getByText("No layout to show")).toBeInTheDocument();
  });

  it("mounts the loaded branch (scrubber + legend + a page-group row) without throwing", () => {
    expect(() =>
      render(
        <LayoutTab
          ir={loadedIR} pages={loadedPages} chunks={loadedChunks} provenance={loadedProvenance}
          error={null} chunksError={null} onRetry={noop} onRetryChunks={noop}
        />,
      ),
    ).not.toThrow();
    expect(screen.getByTestId("page-scrubber")).toBeInTheDocument();
    expect(screen.getByTestId("block-legend")).toBeInTheDocument();
    expect(screen.getAllByTestId("page-group-row").length).toBeGreaterThan(0);
    // The loaded branch must NOT fall through to loading/empty.
    expect(screen.queryByText("loading layout…")).not.toBeInTheDocument();
    expect(screen.queryByText("No layout to show")).not.toBeInTheDocument();
  });

  it("shows the non-blocking chunks-error banner on the loaded branch", () => {
    render(
      <LayoutTab
        ir={loadedIR} pages={loadedPages} chunks={null} provenance={loadedProvenance}
        error={null} chunksError="chunk fetch failed" onRetry={noop} onRetryChunks={noop}
      />,
    );
    // The page/IR view still renders (a page-group row is present) while the banner surfaces the miss.
    expect(screen.getByText(/Chunk provenance is unavailable/)).toBeInTheDocument();
    expect(screen.getAllByTestId("page-group-row").length).toBeGreaterThan(0);
  });
});
