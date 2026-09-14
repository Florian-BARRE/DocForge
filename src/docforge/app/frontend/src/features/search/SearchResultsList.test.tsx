// ====== Code Summary ======
// Render smoke-test covering the two absent-field-safe diagnostics additions: the "scores: <kind>"
// caption next to the result count, and the collapsed-by-default "Diagnostics" disclosure (cost line
// + debug_info rows). An older response with neither field renders neither affordance.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SearchHitModel, SearchResponse } from "../../api/search";
import { ToastProvider } from "../../shell/toast";
import { SearchResultsList } from "./SearchResultsList";

function baseHit(overrides: Partial<SearchHitModel> = {}): SearchHitModel {
  return {
    chunk_id: "chunk-1",
    document_id: "11111111-2222-3333-4444-555555555555",
    filename: "annual-report.pdf",
    score: 0.9,
    text: "Revenue grew 12% year over year.",
    chunk_index: 3,
    token_count: 128,
    ...overrides,
  };
}

function renderList(response: SearchResponse) {
  return render(
    <ToastProvider>
      <SearchResultsList response={response} />
    </ToastProvider>,
  );
}

describe("SearchResultsList diagnostics", () => {
  it("shows the score_kind caption and a Diagnostics disclosure with cost + debug_info", () => {
    const { container } = renderList({
      query: "revenue",
      hits: [baseHit()],
      score_kind: "rrf_fusion",
      debug_info: { rewritten_query: "annual revenue growth" },
      cost: { prompt_tokens: 50, completion_tokens: 20, cost_usd: 0.0012, call_count: 1 },
    });

    expect(screen.getByText("scores: hybrid RRF")).toBeInTheDocument();
    expect(screen.getByText("Diagnostics")).toBeInTheDocument();
    // Collapsed by default, like every other AdvancedDisclosure in the app.
    const details = container.querySelector("details");
    expect(details?.open).toBe(false);
    expect(screen.getByText(/50\+20 tok/)).toBeInTheDocument();
    expect(screen.getByText("rewritten_query")).toBeInTheDocument();
  });

  it("renders neither affordance on an older response with no score_kind/debug_info/cost", () => {
    renderList({ query: "revenue", hits: [baseHit()], debug_info: null });

    expect(screen.queryByText(/^scores:/)).not.toBeInTheDocument();
    expect(screen.queryByText("Diagnostics")).not.toBeInTheDocument();
  });
});
