// ====== Code Summary ======
// Render smoke-test for FailureBreakdownPanel — the empty-window positive state, the populated
// by-cause/by-stage/by-collection lists, and that clicking a bucket bubbles the right selection
// callback (never the non-clickable "unknown" bucket).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FailureBreakdown } from "../../api/jobs";
import { FailureBreakdownPanel } from "./FailureBreakdownPanel";

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  getFailureBreakdown: vi.fn(),
}));

const { getFailureBreakdown } = await import("../../api/jobs");

describe("FailureBreakdownPanel", () => {
  it("shows a positive empty state when nothing failed in the window", async () => {
    const empty: FailureBreakdown = {
      collection_id: null, window_hours: 24, since: "2026-01-01T00:00:00Z", total_failed: 0,
      by_error_type: [], by_stage: [], by_collection: [],
    };
    vi.mocked(getFailureBreakdown).mockResolvedValue(empty);

    render(<FailureBreakdownPanel windowHours={24} onSelectErrorType={vi.fn()} onSelectStage={vi.fn()} onSelectCollection={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("No failures in this window.")).toBeInTheDocument());
  });

  it("renders bucketed causes and reports a click, but never for the 'unknown' bucket", async () => {
    const populated: FailureBreakdown = {
      collection_id: null, window_hours: 24, since: "2026-01-01T00:00:00Z", total_failed: 7,
      by_error_type: [{ label: "TimeoutError", count: 5 }, { label: "unknown", count: 2 }],
      by_stage: [{ label: "embed", count: 5 }],
      by_collection: [{ collection_id: "col-1", collection_name: "Contracts", count: 5 }],
    };
    vi.mocked(getFailureBreakdown).mockResolvedValue(populated);
    const onSelectErrorType = vi.fn();

    render(<FailureBreakdownPanel windowHours={24} onSelectErrorType={onSelectErrorType} onSelectStage={vi.fn()} onSelectCollection={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("TimeoutError")).toBeInTheDocument());
    fireEvent.click(screen.getByText("TimeoutError"));
    expect(onSelectErrorType).toHaveBeenCalledWith("TimeoutError");

    // "unknown" renders as plain (non-interactive) text, not a button.
    expect(screen.getByText("unknown").tagName).not.toBe("BUTTON");
  });
});
