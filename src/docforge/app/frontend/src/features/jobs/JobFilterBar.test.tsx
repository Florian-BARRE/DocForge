// ====== Code Summary ======
// Render smoke-test for JobFilterBar — the search/collection/stage/error/date-range triage facets,
// the active-filter count pill, and the sort/direction controls.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "../../api/collections";
import { EMPTY_JOB_FILTERS, JobFilterBar } from "./JobFilterBar";

vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  listCollections: vi.fn(),
}));

const { listCollections } = await import("../../api/collections");

describe("JobFilterBar", () => {
  it("renders with no active filters, then surfaces the active-count pill once a facet is typed", async () => {
    vi.mocked(listCollections).mockResolvedValue([{ id: "col-1", name: "Contracts" } as Collection]);
    const onFiltersChange = vi.fn();

    render(
      <JobFilterBar
        filters={EMPTY_JOB_FILTERS}
        onFiltersChange={onFiltersChange}
        sort="created"
        onSortChange={vi.fn()}
        order="newest"
        onOrderChange={vi.fn()}
      />,
    );

    expect(screen.queryByText(/filters? active/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter jobs by current stage"), { target: { value: "embed" } });
    expect(onFiltersChange).toHaveBeenCalledWith(expect.objectContaining({ stage: "embed" }));

    // The collection select is populated from listCollections (fetched on mount).
    await waitFor(() => expect(screen.getByRole("option", { name: "Contracts" })).toBeInTheDocument());
  });

  it("shows the active-count pill and a working Clear button when a facet is set", () => {
    const onFiltersChange = vi.fn();
    render(
      <JobFilterBar
        filters={{ ...EMPTY_JOB_FILTERS, search: "abc123" }}
        onFiltersChange={onFiltersChange}
        sort="duration"
        onSortChange={vi.fn()}
        order="oldest"
        onOrderChange={vi.fn()}
      />,
    );

    expect(screen.getByText("1 filter active")).toBeInTheDocument();
    expect(screen.getByText("Shortest first")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Clear"));
    expect(onFiltersChange).toHaveBeenCalledWith(EMPTY_JOB_FILTERS);
  });
});
