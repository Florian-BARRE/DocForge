// ====== Code Summary ======
// Render smoke-test for NewFailuresBanner — renders nothing at zero, then renders + clicking fires
// onViewFailures and advances the localStorage cursor once failures are pending.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NewFailures } from "../../api/jobs";
import { NewFailuresBanner } from "./NewFailuresBanner";

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  getNewFailures: vi.fn(),
}));

const { getNewFailures } = await import("../../api/jobs");

describe("NewFailuresBanner", () => {
  beforeEach(() => localStorage.clear());

  it("renders nothing when there are no new failures", async () => {
    const empty: NewFailures = { since: "2026-01-01T00:00:00Z", count: 0, job_ids: [], latest_failed_at: null };
    vi.mocked(getNewFailures).mockResolvedValue(empty);

    render(<NewFailuresBanner onViewFailures={vi.fn()} />);

    await waitFor(() => expect(getNewFailures).toHaveBeenCalled());
    expect(screen.queryByText(/new failure/)).not.toBeInTheDocument();
  });

  it("shows the count and calls onViewFailures + advances the cursor on click", async () => {
    const withFailures: NewFailures = {
      since: "2026-01-01T00:00:00Z", count: 3, job_ids: ["j1", "j2", "j3"], latest_failed_at: "2026-01-02T00:00:00Z",
    };
    vi.mocked(getNewFailures).mockResolvedValue(withFailures);
    const onViewFailures = vi.fn();

    render(<NewFailuresBanner onViewFailures={onViewFailures} />);

    await waitFor(() => expect(screen.getByText(/3 new failures since your last visit/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button"));

    expect(onViewFailures).toHaveBeenCalled();
    expect(localStorage.getItem("docforge_jobs_last_seen_failures_at")).toBe("2026-01-02T00:00:00Z");
  });
});
