// ====== Code Summary ======
// Covers the bulk re-ingest success toast surfacing `skipped_in_flight` (documents the per-document
// active-job lock refused a second run for) — the toast must name the count when it's > 0, and stay
// silent about it when 0, matching the enqueued/capped wording already covered by this component.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { BulkReingestResponse } from "../../api/corpus";
import { ToastProvider } from "../../shell/toast";
import { BulkActionBar } from "./BulkActionBar";

function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/corpus", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/corpus")>()),
  bulkReingestDocuments: vi.fn(),
}));

const { bulkReingestDocuments } = await import("../../api/corpus");

function reingestResponse(overrides: Partial<BulkReingestResponse>): BulkReingestResponse {
  return {
    collection_id: "col-1",
    matched: 3,
    enqueued: 3,
    capped: false,
    max_fanout: 500,
    skipped_in_flight: 0,
    jobs: [],
    ...overrides,
  };
}

/** Opens the confirm dialog then clicks its own "Re-ingest" confirm button — scoped to the dialog
 *  since the bar's trigger button shares the same accessible name. */
function confirmReingest() {
  fireEvent.click(screen.getByRole("button", { name: "Re-ingest" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Re-ingest" }));
}

describe("BulkActionBar — bulk re-ingest result toast", () => {
  it("reports skipped_in_flight when documents were skipped as already in flight", async () => {
    vi.mocked(bulkReingestDocuments).mockResolvedValue(reingestResponse({ matched: 5, enqueued: 3, skipped_in_flight: 2 }));

    renderWithProviders(
      <BulkActionBar collectionId="col-1" count={5} buildSelector={() => ({ document_ids: ["a", "b"] })} onDone={vi.fn()} />,
    );

    confirmReingest();

    await waitFor(() => expect(screen.getByText(/Queued 3 of 5 documents for re-ingestion/)).toBeInTheDocument());
    expect(screen.getByText(/2 skipped — already in flight/)).toBeInTheDocument();
  });

  it("says nothing about skipped_in_flight when none were skipped", async () => {
    vi.mocked(bulkReingestDocuments).mockResolvedValue(reingestResponse({ matched: 3, enqueued: 3, skipped_in_flight: 0 }));

    renderWithProviders(
      <BulkActionBar collectionId="col-1" count={3} buildSelector={() => ({ document_ids: ["a"] })} onDone={vi.fn()} />,
    );

    confirmReingest();

    await waitFor(() => expect(screen.getByText(/Queued 3 of 3 documents for re-ingestion/)).toBeInTheDocument());
    expect(screen.queryByText(/already in flight/)).not.toBeInTheDocument();
  });
});
