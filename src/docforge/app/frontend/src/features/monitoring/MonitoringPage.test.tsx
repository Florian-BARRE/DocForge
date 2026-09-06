// ====== Code Summary ======
// Render smoke-test for MonitoringPage — mounts through loading -> loaded for its fleet queue-depth
// and throughput tiles, the live per-worker CPU/mem dashboard (including a worker reporting no
// resource fields at all), the recent-completed-jobs panel, and asserts the telemetry note is now a
// secondary footnote (not the page's primary content) while navigating from the recent-jobs list
// still works.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { JobPage, QueueDepth, WorkersLive } from "../../api/jobs";
import type { Navigate } from "../../shell/view";
import { ToastProvider } from "../../shell/toast";
import { MonitoringPage } from "./MonitoringPage";

// JobRow (rendered by RecentJobsPanel) renders JobCancelControl, which calls useToast()
// unconditionally — needs a real provider (see agent-memory/frontend/quality-gate-lint-test.md's
// ToastProvider harness gotcha).
function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  getQueueDepth: vi.fn(),
  listJobsPage: vi.fn(),
  getWorkersLive: vi.fn(),
}));

const { getQueueDepth, listJobsPage, getWorkersLive } = await import("../../api/jobs");

describe("MonitoringPage", () => {
  it("mounts through loading -> loaded without throwing, rendering live worker CPU/mem and a demoted telemetry footnote", async () => {
    const queueDepth: QueueDepth = { pending: 2, running: 0 };
    const donePage: JobPage = {
      total: 1, limit: 100, offset: 0,
      jobs: [
        {
          job_id: "job-1", document_id: "doc-1", document_filename: "a.pdf", document_title: null,
          collection_id: "col-1", collection_name: "Contracts", status: "done", cancel_requested: false,
          progress: 100, current_stage: null, error: null, attempt: 1, started_at: "2026-01-01T00:00:00Z",
          finished_at: new Date().toISOString(), updated_at: new Date().toISOString(), stalled: false,
          total_prompt_tokens: 0, total_completion_tokens: 0, cost_usd: 0, items_done: null, items_total: null,
          failed_node_id: null, failed_node_kind: null, failed_item_index: null, error_type: null,
        },
      ],
    };
    const workersLive: WorkersLive = {
      workers: [
        {
          worker_id: "w1", worker_name: "worker-a", alive: true, busy: true, last_seen: new Date().toISOString(),
          started_at: new Date(Date.now() - 3_600_000).toISOString(), max_jobs: 4,
          cpu_percent: 142.3, mem_mb: 812, mem_percent: 12.5, jobs: [],
        },
        // A worker reporting no resource fields at all — must render "not reported", never throw
        // or fabricate a number (an old heartbeat row / a non-sampling build).
        {
          worker_id: "w2", worker_name: null, alive: false, busy: false, last_seen: null,
          started_at: null, max_jobs: null, cpu_percent: null, mem_mb: null, mem_percent: null, jobs: [],
        },
      ],
    };
    vi.mocked(getQueueDepth).mockResolvedValue(queueDepth);
    vi.mocked(listJobsPage).mockResolvedValue(donePage);
    vi.mocked(getWorkersLive).mockResolvedValue(workersLive);

    const onNavigate: Navigate = vi.fn();
    expect(() => renderWithProviders(<MonitoringPage onNavigate={onNavigate} />)).not.toThrow();

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
    expect(screen.getByText("1", { exact: true })).toBeInTheDocument(); // throughput within the trailing window

    // The live per-worker CPU/mem dashboard is the page's main content now.
    await waitFor(() => expect(screen.getByText("worker-a")).toBeInTheDocument());
    expect(screen.getByText("142.3%")).toBeInTheDocument();
    expect(screen.getByText("Memory · 812 MB")).toBeInTheDocument();
    expect(screen.getAllByText("not reported").length).toBeGreaterThan(0); // the null-fields worker

    // The telemetry note still exists but is now a secondary footnote, not the primary content.
    expect(screen.getByText(/docforge-overview/)).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("a.pdf")).toBeInTheDocument());
    fireEvent.click(screen.getByText("a.pdf"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "job", collectionId: "col-1", jobId: "job-1" });
  });
});
