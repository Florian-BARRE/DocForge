// ====== Code Summary ======
// Render smoke-test for the panel's third scope — "Selected documents". The default two scopes
// (pending/all) must keep sending only `scope`; picking "Selected documents" and applying a filter
// control must send an explicit `filter` body instead — the whole point of this task (letting the
// user pick WHICH documents an estimate covers from the Overview panel, not just pending/all).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CostEstimate } from "../../../api/collections";
import { ToastProvider } from "../../../shell/toast";
import { CostEstimatePanel } from "./CostEstimatePanel";

vi.mock("../../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/collections")>()),
  estimateCollectionCost: vi.fn(),
  updateCollection: vi.fn(),
}));

const { estimateCollectionCost } = await import("../../../api/collections");

const baseEstimate: CostEstimate = {
  document_count: 3,
  stages: [],
  volume: { pages: 3, chunks: 9, dense_vectors: 9, sparse_vectors: 9, storage_bytes: 1024 },
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_cost_usd: 0,
  cost_complete: true,
  assumptions: {},
  caveats: [],
};

function renderPanel() {
  return render(
    <ToastProvider>
      <CostEstimatePanel collectionId="col-1" supportedFormats={["pdf"]} estimateOverrides={null} onOverridesSaved={() => {}} />
    </ToastProvider>,
  );
}

describe("CostEstimatePanel", () => {
  it("sends only the scope on the default 'pending' tab", async () => {
    vi.mocked(estimateCollectionCost).mockResolvedValue(baseEstimate);
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /estimate cost/i }));

    await waitFor(() => expect(estimateCollectionCost).toHaveBeenCalledWith("col-1", "pending"));
  });

  it("sends only the scope on the 'Whole collection' tab", async () => {
    vi.mocked(estimateCollectionCost).mockResolvedValue(baseEstimate);
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Whole collection" }));
    fireEvent.click(screen.getByRole("button", { name: /estimate cost/i }));

    await waitFor(() => expect(estimateCollectionCost).toHaveBeenCalledWith("col-1", "all"));
  });

  it("sends a document filter subset on the 'Selected documents' tab", async () => {
    vi.mocked(estimateCollectionCost).mockResolvedValue(baseEstimate);
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Selected documents" }));
    // The caption reflects the not-yet-filtered state before any control is touched.
    expect(screen.getByText(/no filters applied yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "true" }));
    fireEvent.click(screen.getByRole("button", { name: /estimate cost/i }));

    await waitFor(() =>
      expect(estimateCollectionCost).toHaveBeenCalledWith("col-1", "pending", { filter: { enabled: true } }),
    );
  });
});
