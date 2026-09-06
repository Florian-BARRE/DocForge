// ====== Code Summary ======
// Render smoke-test for JobRerunControl — the quick re-run action on the job detail page. Covers
// the happy path (reingestDocument called, navigate to the new job), the 409 "already active" toast
// path, and the hidden-while-running case (the core repro for "no button to re-run it quickly").

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { JobStatus } from "../../api/jobs";
import type { UploadAccepted } from "../../api/documents";
import { HttpError } from "../../api/http";
import type { Navigate } from "../../shell/view";
import { ToastProvider } from "../../shell/toast";
import { JobRerunControl } from "./JobRerunControl";

function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/documents")>()),
  reingestDocument: vi.fn(),
}));

const { reingestDocument } = await import("../../api/documents");

function jobFixture(overrides: Partial<JobStatus>): JobStatus {
  return {
    job_id: "job-1", document_id: "doc-1", document_filename: "report.pdf", document_title: null,
    collection_id: "col-1", collection_name: "Contracts", status: "failed", cancel_requested: false,
    progress: 40, current_stage: "embed", error: "boom", attempt: 1, started_at: "2026-01-01T00:00:00Z",
    finished_at: null, updated_at: new Date().toISOString(), stalled: false,
    total_prompt_tokens: 0, total_completion_tokens: 0, cost_usd: 0, items_done: null, items_total: null,
    failed_node_id: null, failed_node_kind: null, failed_item_index: null, error_type: null,
    ...overrides,
  } as JobStatus;
}

describe("JobRerunControl", () => {
  it("re-runs the document and navigates to the freshly created job on success", async () => {
    const accepted: UploadAccepted = { document_id: "doc-1", job_id: "job-2", duplicate: false };
    vi.mocked(reingestDocument).mockResolvedValue(accepted);
    const onNavigate: Navigate = vi.fn();

    renderWithProviders(<JobRerunControl job={jobFixture({})} collectionId="col-1" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("Re-run"));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith({ name: "job", collectionId: "col-1", jobId: "job-2" }));
    expect(reingestDocument).toHaveBeenCalledWith("doc-1", { force: false });
  });

  it("toasts a friendly message on a 409 ALREADY_ACTIVE conflict and does not navigate", async () => {
    vi.mocked(reingestDocument).mockRejectedValue(new HttpError(409, [{ message: "already active" }]));
    const onNavigate: Navigate = vi.fn();

    renderWithProviders(<JobRerunControl job={jobFixture({ status: "done" })} collectionId="col-1" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("Re-run"));

    await waitFor(() => expect(screen.getByText(/already active/i)).toBeInTheDocument());
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("renders no re-run button while the job is still pending/running", () => {
    const onNavigate: Navigate = vi.fn();
    renderWithProviders(
      <JobRerunControl job={jobFixture({ status: "running" })} collectionId="col-1" onNavigate={onNavigate} />,
    );
    // The control renders nothing actionable mid-run (the ToastProvider's own portal container aside).
    expect(screen.queryByRole("button", { name: /re-?run|reingest/i })).toBeNull();
  });
});
