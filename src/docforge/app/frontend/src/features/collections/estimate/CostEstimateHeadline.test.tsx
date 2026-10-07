// ====== Code Summary ======
// Render test for the estimate headline's honesty contract: a null total (some paid stage unpriced)
// shows the priced lower bound as a minimum ("≥ $X") with the "partial" chip — never a bare figure
// that reads as the full total — while a complete zero still reads "Free".

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CostEstimate } from "../../../api/collections";
import { CostEstimateHeadline } from "./CostEstimateHeadline";

const base: CostEstimate = {
  document_count: 2,
  stages: [],
  volume: { pages: 2, chunks: 4, dense_vectors: 4, sparse_vectors: 4, storage_bytes: 2048 },
  total_prompt_tokens: 100,
  total_completion_tokens: 20,
  total_cost_usd: 0,
  total_cost_lower_bound_usd: 0,
  cost_complete: true,
  assumptions: {},
  caveats: [],
};

describe("CostEstimateHeadline", () => {
  it("shows the lower bound with ≥ and the partial chip when the total is null", () => {
    render(
      <CostEstimateHeadline
        estimate={{ ...base, total_cost_usd: null, total_cost_lower_bound_usd: 1.5, cost_complete: false }}
      />,
    );
    expect(screen.getByText(/^≥ /)).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    expect(screen.queryByText("Free")).not.toBeInTheDocument();
  });

  it("never reads a null total with a zero lower bound as Free", () => {
    render(
      <CostEstimateHeadline
        estimate={{ ...base, total_cost_usd: null, total_cost_lower_bound_usd: 0, cost_complete: false }}
      />,
    );
    expect(screen.getByText(/^≥ /)).toBeInTheDocument();
    expect(screen.queryByText("Free")).not.toBeInTheDocument();
  });

  it("keeps a complete zero as Free without the chip", () => {
    render(<CostEstimateHeadline estimate={base} />);
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.queryByText("partial")).not.toBeInTheDocument();
  });
});
