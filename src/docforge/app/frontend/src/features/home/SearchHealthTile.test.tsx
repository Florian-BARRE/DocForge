// ====== Code Summary ======
// Render smoke-test for SearchHealthTile — covers the healthy-with-data state (counts/latency/rates
// rendered) and the total_runs===0 empty state, mirroring the sibling cockpit tiles' own tests.

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SearchHealthSummary } from "../../api/search";
import type { Navigate } from "../../shell/view";
import { SearchHealthTile } from "./SearchHealthTile";

vi.mock("../../api/search", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/search")>()),
  getSearchHealth: vi.fn(),
}));

const { getSearchHealth } = await import("../../api/search");

describe("SearchHealthTile", () => {
  it("renders the healthy-with-data state", async () => {
    const data: SearchHealthSummary = {
      total_runs: 42, error_rate: 0.02, p95_latency_ms: 962, zero_result_rate: 0.05, avg_hits: 6.4,
    };
    vi.mocked(getSearchHealth).mockResolvedValue(data);
    const onNavigate: Navigate = vi.fn();

    expect(() => render(<SearchHealthTile onNavigate={onNavigate} />)).not.toThrow();

    await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
    expect(screen.getByText("962 ms")).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(screen.getByText("2%")).toBeInTheDocument();
  });

  it("shows the empty state when no searches have run yet", async () => {
    const data: SearchHealthSummary = {
      total_runs: 0, error_rate: 0, p95_latency_ms: null, zero_result_rate: 0, avg_hits: null,
    };
    vi.mocked(getSearchHealth).mockResolvedValue(data);
    const onNavigate: Navigate = vi.fn();

    render(<SearchHealthTile onNavigate={onNavigate} />);

    await waitFor(() => expect(screen.getByText("No searches yet")).toBeInTheDocument());
  });
});
