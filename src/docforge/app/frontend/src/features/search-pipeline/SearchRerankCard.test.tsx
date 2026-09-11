// ====== Code Summary ======
// Regression test for round-4 T9: the reranking step must surface an amber caveat while off,
// matching the ingestion stage rail's own "ships off" note for provider-hosted stages — including
// the local-CPU-not-recommended warning — and say nothing once enabled.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SearchRerankCard } from "./SearchRerankCard";

describe("SearchRerankCard — off-state caveat", () => {
  it("shows the ships-off / local-CPU-not-recommended note while disabled", () => {
    render(<SearchRerankCard step={5} enabled={false} onToggle={vi.fn()} />);
    expect(screen.getByText(/Provider-hosted — ships off/)).toBeInTheDocument();
    expect(screen.getByText(/local CPU reranker is NOT recommended/)).toBeInTheDocument();
  });

  it("shows no caveat once reranking is enabled", () => {
    render(<SearchRerankCard step={5} enabled onToggle={vi.fn()} />);
    expect(screen.queryByText(/ships off/)).not.toBeInTheDocument();
  });
});
