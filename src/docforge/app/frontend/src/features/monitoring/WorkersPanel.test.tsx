// ====== Code Summary ======
// Render smoke-test for WorkersPanel — mounts through loading -> loaded with one worker + the
// fleet summary/recent-activity backfill panels, and asserts it never throws (JobRow inside both
// the worker card and the recent-activity panel renders JobCancelControl, which calls useToast()
// unconditionally — needs a real ToastProvider, see agent-memory/frontend/quality-gate-lint-test.md).

import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { JobPage, JobStatus, WorkersLive } from "../../api/jobs";
import type { Navigate } from "../../shell/view";
import { ToastProvider } from "../../shell/toast";
import { WorkersPanel } from "./WorkersPanel";

function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  getWorkersLive: vi.fn(),
  listJobsPage: vi.fn(),
}));

const { getWorkersLive, listJobsPage } = await import("../../api/jobs");

function jobFixture(overrides: Partial<JobStatus>): JobStatus {
  return {
    job_id: "job-1", document_id: "doc-1", document_filename: "report.pdf", document_title: null,
    collection_id: "col-1", collection_name: "Contracts", status: "running", cancel_requested: false,
    progress: 40, current_stage: "embed", error: null, attempt: 1, started_at: "2026-01-01T00:00:00Z",
    finished_at: null, updated_at: new Date().toISOString(), stalled: false,
    total_prompt_tokens: 0, total_completion_tokens: 0, cost_usd: 0, items_done: null, items_total: null,
    failed_node_id: null, failed_node_kind: null, failed_item_index: null, error_type: null,
    ...overrides,
  };
}

describe("WorkersPanel", () => {
  it("mounts through loading -> loaded, showing the fleet summary + recent activity panels", async () => {
    const runningJob = jobFixture({});
    const workers: WorkersLive = {
      workers: [
        { worker_id: "w1", worker_name: "worker-a", alive: true, busy: true, last_seen: new Date().toISOString(), started_at: null, max_jobs: 4, cpu_percent: 42.5, mem_mb: 512, mem_percent: 6.4, jobs: [runningJob] },
      ],
    };
    const recentPage: JobPage = { total: 1, limit: 8, offset: 0, jobs: [runningJob] };
    vi.mocked(getWorkersLive).mockResolvedValue(workers);
    vi.mocked(listJobsPage).mockResolvedValue(recentPage);

    const onNavigate: Navigate = vi.fn();
    expect(() => renderWithProviders(<WorkersPanel onNavigate={onNavigate} />)).not.toThrow();

    await waitFor(() => expect(screen.getByText("worker-a")).toBeInTheDocument());
    expect(screen.getByText("Fleet capacity")).toBeInTheDocument();
    expect(screen.getByText("Recent activity across the fleet")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("report.pdf").length).toBeGreaterThan(0));
  });
});
