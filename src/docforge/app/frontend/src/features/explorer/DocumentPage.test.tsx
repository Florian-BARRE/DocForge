// ====== Code Summary ======
// Render smoke-test for the "0-chunk = success-with-warning" vertical: a DONE document that carries
// a non-null `warning_reason` (chunk_count 0) must render its warning affordance — the warn-toned
// status dot (DocumentStatusChip) and the "0 chunks" Chip — without throwing. Mirrors
// CollectionOverview.test.tsx's loading->loaded pattern (ToastProvider harness, mocked fetch).

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DocumentDetail } from "../../api/explorer";
import { ToastProvider } from "../../shell/toast";
import { DocumentPage } from "./DocumentPage";

vi.mock("../../api/explorer", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/explorer")>()),
  getDocument: vi.fn(),
  // The overview tab warms pages too (its System metadata panel's page-scan summary) — mocked here
  // so the render smoke-test doesn't hit an unmocked fetch.
  getDocumentPages: vi.fn(),
}));

const { getDocument, getDocumentPages } = await import("../../api/explorer");

const warnedDocument: DocumentDetail = {
  id: "doc-1",
  collection_id: "col-1",
  filename: "empty-scan.pdf",
  format: "pdf",
  mime_type: "application/pdf",
  file_size: 1234,
  page_count: 3,
  language: "en",
  title: "Empty Scan",
  source_kind: "scanned",
  status: "done",
  source_hash: "abc123",
  pdf_blob_hash: null,
  simhash: null,
  pipeline_version: "v1",
  created_at: "2026-01-01T00:00:00Z",
  enabled: true,
  chunk_count: 0,
  warning_reason: "No chunks were produced — every page was classified as boilerplate.",
  metadata: [],
};

describe("DocumentPage — done-with-warning document", () => {
  it("renders the 0-chunk warning affordance without throwing", async () => {
    vi.mocked(getDocument).mockResolvedValue(warnedDocument);
    vi.mocked(getDocumentPages).mockResolvedValue([]);

    expect(() =>
      render(
        <ToastProvider>
          <DocumentPage collectionId="col-1" documentId="doc-1" onNavigate={vi.fn()} />
        </ToastProvider>,
      ),
    ).not.toThrow();

    expect(screen.getByText("loading document…")).toBeInTheDocument();

    // The System metadata panel's "Source" group also shows the filename (see SystemMetadataPanel),
    // so this now matches twice — scope to the page's own <h1> title, which is unique.
    await waitFor(() => expect(screen.getByRole("heading", { name: "empty-scan.pdf" })).toBeInTheDocument());
    expect(screen.queryByText("loading document…")).not.toBeInTheDocument();

    // The warn-toned "0 chunks" Chip, titled with the full warning_reason.
    const warningChip = screen.getByText("0 chunks");
    expect(warningChip).toBeInTheDocument();
    expect(warningChip.closest("span")?.getAttribute("title")).toBe(warnedDocument.warning_reason);

    // The status chip itself stays "done" (a warning is never a failure) but is titled to flag it.
    // It now renders twice — once in the page header, once inside the System metadata panel's own
    // "Status" group (same DocumentStatusChip) — both must carry the warning title.
    const statusChips = screen.getAllByText("done");
    expect(statusChips).toHaveLength(2);
    for (const chip of statusChips) expect(chip.closest("span")?.getAttribute("title")).toBe("Completed with a warning");
  });
});
