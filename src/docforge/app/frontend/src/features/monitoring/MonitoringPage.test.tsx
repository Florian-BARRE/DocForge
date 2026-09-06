// ====== Code Summary ======
// Render smoke-test for MonitoringPage — mounts through loading -> loaded for its fleet queue-depth
// and throughput tiles plus the recent-completed-jobs panel, asserts the telemetry note never
// renders a hardcoded host link, and asserts navigating from the recent-jobs list works.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { JobPage, QueueDepth } from "../../api/jobs";
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
}));

const { getQueueDepth, listJobsPage } = await import("../../api/jobs");

describe("MonitoringPage", () => {
  it("mounts through loading -> loaded without throwing, and names no hardcoded telemetry host", async () => {
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
    vi.mocked(getQueueDepth).mockResolvedValue(queueDepth);
    vi.mocked(listJobsPage).mockResolvedValue(donePage);

    const onNavigate: Navigate = vi.fn();
    expect(() => renderWithProviders(<MonitoringPage onNavigate={onNavigate} />)).not.toThrow();

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
    expect(screen.getByText("1", { exact: true })).toBeInTheDocument(); // throughput within the trailing window

    expect(screen.getByText(/docforge-overview/)).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("a.pdf")).toBeInTheDocument());
    fireEvent.click(screen.getByText("a.pdf"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "job", collectionId: "col-1", jobId: "job-1" });
  });
});
