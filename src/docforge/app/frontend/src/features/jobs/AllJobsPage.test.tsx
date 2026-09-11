// ====== Code Summary ======
// Render smoke-test for AllJobsPage — mounts through loading -> loaded on the default "All" tab
// (the full fleet queue, newest-first, no status filter; worker column shows the honest "—", never
// a fabricated id) and covers switching to Pending (FIFO oldest-first) and Running (worker column
// joins the live worker feed instead).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FailureBreakdown, JobPage, JobStatus, JobTimeseries, NewFailures, WorkersLive } from "../../api/jobs";
import type { Navigate } from "../../shell/view";
import { ToastProvider } from "../../shell/toast";
import { AllJobsPage } from "./AllJobsPage";

// JobRow renders JobCancelControl, which calls useToast() unconditionally — needs a real provider
// (see agent-memory/frontend/quality-gate-lint-test.md's ToastProvider harness gotcha).
function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  listJobsPage: vi.fn(),
  getWorkersLive: vi.fn(),
  getFailureBreakdown: vi.fn(),
  getJobTimeseries: vi.fn(),
  getNewFailures: vi.fn(),
}));
vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  listCollections: vi.fn(),
}));

const { listJobsPage, getWorkersLive, getFailureBreakdown, getJobTimeseries, getNewFailures } = await import("../../api/jobs");
const { listCollections } = await import("../../api/collections");

const emptyBreakdown: FailureBreakdown = {
  collection_id: null, window_hours: 24, since: "2026-01-01T00:00:00Z", total_failed: 0,
  by_error_type: [], by_stage: [], by_collection: [],
};
const emptyTimeseries: JobTimeseries = { collection_id: null, window_hours: 24, bucket_seconds: 3600, buckets: [] };
const noNewFailures: NewFailures = { since: "2026-01-01T00:00:00Z", count: 0, job_ids: [], latest_failed_at: null };

function jobFixture(overrides: Partial<JobStatus>): JobStatus {
  return {
    job_id: "job-1",
    document_id: "doc-1",
    document_filename: "report.pdf",
    document_title: null,
    collection_id: "col-1",
    collection_name: "Contracts",
    status: "pending",
    cancel_requested: false,
    progress: 0,
    current_stage: null,
    error: null,
    attempt: 1,
    started_at: null,
    finished_at: null,
    updated_at: "2026-01-01T00:00:00Z",
    stalled: false,
    duration_seconds: null,
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    cost_usd: 0,
    items_done: null,
    items_total: null,
    failed_node_id: null,
    failed_node_kind: null,
    failed_item_index: null,
    error_type: null,
    ...overrides,
  };
}

const emptyWorkers: WorkersLive = { workers: [] };

describe("AllJobsPage", () => {
  beforeEach(() => {
    vi.mocked(getFailureBreakdown).mockResolvedValue(emptyBreakdown);
    vi.mocked(getJobTimeseries).mockResolvedValue(emptyTimeseries);
    vi.mocked(getNewFailures).mockResolvedValue(noNewFailures);
    vi.mocked(listCollections).mockResolvedValue([]);
  });

  it("mounts through loading -> loaded on the default 'All' tab, showing an honest '—' worker (never fabricated)", async () => {
    const allPage: JobPage = { total: 1, limit: 25, offset: 0, jobs: [jobFixture({ status: "pending" })] };
    vi.mocked(listJobsPage).mockResolvedValue(allPage);
    vi.mocked(getWorkersLive).mockResolvedValue(emptyWorkers);

    const onNavigate: Navigate = vi.fn();
    expect(() => renderWithProviders(<AllJobsPage onNavigate={onNavigate} />)).not.toThrow();

    expect(screen.getByText("loading jobs…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("report.pdf")).toBeInTheDocument());
    expect(screen.queryByText("loading jobs…")).not.toBeInTheDocument();

    // The "All" tab carries no status filter and reads newest-first — the full queue, in order.
    expect(listJobsPage).toHaveBeenCalledWith(expect.objectContaining({ status: undefined, order: "newest" }));
    expect(screen.getByText(/worker —/)).toBeInTheDocument();
  });

  it("switches to the Pending tab, which filters to FIFO oldest-first order", async () => {
    const pendingPage: JobPage = { total: 1, limit: 25, offset: 0, jobs: [jobFixture({ status: "pending" })] };
    vi.mocked(listJobsPage).mockResolvedValue(pendingPage);
    vi.mocked(getWorkersLive).mockResolvedValue(emptyWorkers);

    renderWithProviders(<AllJobsPage onNavigate={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("report.pdf")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Pending"));

    await waitFor(() =>
      expect(listJobsPage).toHaveBeenCalledWith(expect.objectContaining({ status: ["pending"], order: "oldest" })),
    );
  });

  it("shows the real worker on the Running tab, joined from the live worker feed", async () => {
    const runningJob = jobFixture({ status: "running", current_stage: "embed" });
    const runningPage: JobPage = { total: 1, limit: 25, offset: 0, jobs: [runningJob] };
    vi.mocked(listJobsPage).mockImplementation(async ({ status } = {}) =>
      status?.includes("running") ? runningPage : { total: 0, limit: 25, offset: 0, jobs: [] },
    );
    vi.mocked(getWorkersLive).mockResolvedValue({
      workers: [{ worker_id: "w1", worker_name: "worker-a", alive: true, busy: true, last_seen: null, started_at: null, max_jobs: null, cpu_percent: null, mem_mb: null, mem_percent: null, jobs: [runningJob] }],
    });

    renderWithProviders(<AllJobsPage onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByText("Running"));

    await waitFor(() => expect(screen.getByText("report.pdf")).toBeInTheDocument());
    expect(screen.getByText("worker-a")).toBeInTheDocument();
  });
});
