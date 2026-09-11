// ====== Code Summary ======
// Render smoke-test for JobTrendsPanel — mounts through loading -> loaded with a populated hourly
// series and asserts the three sparkline rows (done/failed/backlog) render with their latest value.

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { JobTimeseries } from "../../api/jobs";
import { JobTrendsPanel } from "./JobTrendsPanel";

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  getJobTimeseries: vi.fn(),
}));

const { getJobTimeseries } = await import("../../api/jobs");

describe("JobTrendsPanel", () => {
  it("mounts and renders the three trend sparklines with their latest-bucket value", async () => {
    const series: JobTimeseries = {
      collection_id: null, window_hours: 24, bucket_seconds: 3600,
      buckets: [
        { bucket_start: "2026-01-01T00:00:00Z", created: 3, done: 2, failed: 0, backlog: 1 },
        { bucket_start: "2026-01-01T01:00:00Z", created: 1, done: 4, failed: 1, backlog: 3 },
      ],
    };
    vi.mocked(getJobTimeseries).mockResolvedValue(series);

    expect(() => render(<JobTrendsPanel windowHours={24} onWindowHoursChange={vi.fn()} />)).not.toThrow();

    await waitFor(() => expect(screen.getByRole("img", { name: "Done/h trend" })).toBeInTheDocument());
    expect(screen.getByRole("img", { name: "Failed/h trend" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Backlog trend" })).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument(); // latest done/h
    expect(screen.getByText("3")).toBeInTheDocument(); // latest backlog
  });
});
