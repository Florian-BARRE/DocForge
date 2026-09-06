// ====== Code Summary ======
// Render smoke-test for AllJobsPage — mounts through loading -> loaded on the default Pending tab
// (worker column shows the honest "—", never a fabricated id) and covers switching to Running
// (worker column joins the live worker feed instead).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { JobPage, JobStatus, WorkersLive } from "../../api/jobs";
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
}));

const { listJobsPage, getWorkersLive } = await import("../../api/jobs");

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
  it("mounts through loading -> loaded on the Pending tab, showing an honest '—' worker (never fabricated)", async () => {
    const pendingPage: JobPage = { total: 1, limit: 25, offset: 0, jobs: [jobFixture({ status: "pending" })] };
    vi.mocked(listJobsPage).mockResolvedValue(pendingPage);
    vi.mocked(getWorkersLive).mockResolvedValue(emptyWorkers);

    const onNavigate: Navigate = vi.fn();
    expect(() => renderWithProviders(<AllJobsPage onNavigate={onNavigate} />)).not.toThrow();

    expect(screen.getByText("loading jobs…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("report.pdf")).toBeInTheDocument());
    expect(screen.queryByText("loading jobs…")).not.toBeInTheDocument();

    // Pending order is FIFO (oldest-first) and never claims a worker before claim time.
    expect(listJobsPage).toHaveBeenCalledWith(expect.objectContaining({ status: ["pending"], order: "oldest" }));
    expect(screen.getByText(/worker —/)).toBeInTheDocument();
  });

  it("shows the real worker on the Running tab, joined from the live worker feed", async () => {
    const runningJob = jobFixture({ status: "running", current_stage: "embed" });
    const runningPage: JobPage = { total: 1, limit: 25, offset: 0, jobs: [runningJob] };
    vi.mocked(listJobsPage).mockImplementation(async ({ status } = {}) =>
      status?.includes("running") ? runningPage : { total: 0, limit: 25, offset: 0, jobs: [] },
    );
    vi.mocked(getWorkersLive).mockResolvedValue({
      workers: [{ worker_id: "w1", worker_name: "worker-a", alive: true, busy: true, last_seen: null, started_at: null, max_jobs: null, jobs: [runningJob] }],
    });

    renderWithProviders(<AllJobsPage onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByText("Running"));

    await waitFor(() => expect(screen.getByText("report.pdf")).toBeInTheDocument());
    expect(screen.getByText("worker-a")).toBeInTheDocument();
  });
});
