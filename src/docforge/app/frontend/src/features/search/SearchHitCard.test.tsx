// ====== Code Summary ======
// Render smoke-test for the audit fix that replaced the raw bold-accent RRF float with a coarse
// relevance bucket + filename-led citation. Covers: a top-scoring hit renders "High relevance" and
// its filename, the raw score is NOT in the DOM until the "technical score" toggle is clicked, and a
// weak hit (low ratio to the result set's top score) renders "Low relevance" instead.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SearchHitModel } from "../../api/search";
import { ToastProvider } from "../../shell/toast";
import { SearchHitCard } from "./SearchHitCard";

function baseHit(overrides: Partial<SearchHitModel>): SearchHitModel {
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

describe("SearchHitCard", () => {
  it("renders a High relevance bucket and the filename, raw score hidden until toggled", () => {
    render(
      <ToastProvider>
        <SearchHitCard hit={baseHit({ score: 0.95 })} topScore={1.0} />
      </ToastProvider>,
    );

    expect(screen.getByText("High relevance")).toBeInTheDocument();
    expect(screen.getByText("annual-report.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/raw score/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("technical score"));
    expect(screen.getByText("raw score 0.9500")).toBeInTheDocument();
  });

  it("renders a Low relevance bucket for a hit far below the result set's top score", () => {
    render(
      <ToastProvider>
        <SearchHitCard hit={baseHit({ score: 0.1 })} topScore={1.0} />
      </ToastProvider>,
    );

    expect(screen.getByText("Low relevance")).toBeInTheDocument();
  });
});
