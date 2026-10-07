// ====== Code Summary ======
// Stage-replay bulk reingest: the stage select sends `replayFrom`, a 409 estimate_required shows the
// estimate and the "Confirm and reingest" re-post carries `confirmEstimate`, a 429 shows the
// retry-after message, and skipped_not_replayable is named in the result toast.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "../../api/http";
import { ToastProvider } from "../../shell/toast";
import { BulkActionBar } from "./BulkActionBar";

vi.mock("../../api/corpus", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/corpus")>()),
  bulkReingestDocuments: vi.fn(),
}));

const { bulkReingestDocuments } = await import("../../api/corpus");
const mocked = vi.mocked(bulkReingestDocuments);

const OK = { collection_id: "c", matched: 4, enqueued: 3, capped: false, max_fanout: 500, skipped_in_flight: 0, skipped_not_replayable: 1, jobs: [] };

function openDialog() {
  render(
    <ToastProvider>
      <BulkActionBar collectionId="c" count={4} buildSelector={() => ({ document_ids: ["a"] })} onDone={vi.fn()} />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Re-ingest" }));
  return screen.getByRole("dialog");
}

describe("BulkActionBar — stage replay", () => {
  beforeEach(() => mocked.mockReset());

  it("sends the chosen stage as replayFrom and names skipped_not_replayable", async () => {
    mocked.mockResolvedValue(OK);
    const dialog = openDialog();
    fireEvent.change(within(dialog).getByLabelText("Replay from stage"), { target: { value: "embed" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Re-ingest" }));

    await waitFor(() => expect(mocked).toHaveBeenCalledWith("c", { document_ids: ["a"] }, { replayFrom: "embed", confirmEstimate: false }));
    await waitFor(() => expect(screen.getByText(/1 skipped — no persisted IR to replay/)).toBeInTheDocument());
  });

  it("shows the estimate on 409 and re-posts with confirmEstimate", async () => {
    const estimate = {
      document_count: 300, total_cost_usd: 1.5, total_cost_lower_bound_usd: 1.2, cost_complete: false,
      priced_stages: ["embed"], caveats: ["metagen unpriced"],
    };
    mocked.mockRejectedValueOnce(
      new HttpError(409, [{ message: "big" }], { detail: { code: "estimate_required", message: "big", matched: 300, threshold: 200, estimate } }),
    );
    mocked.mockResolvedValueOnce(OK);
    const dialog = openDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "Re-ingest" }));

    await waitFor(() => expect(within(dialog).getByText("metagen unpriced")).toBeInTheDocument());
    expect(within(dialog).getByText(/at least/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm and reingest" }));

    await waitFor(() => expect(mocked).toHaveBeenLastCalledWith("c", { document_ids: ["a"] }, { replayFrom: null, confirmEstimate: true }));
  });

  it("shows the queue-full message with Retry-After on 429", async () => {
    mocked.mockRejectedValueOnce(
      new HttpError(429, [{ message: "full" }], { detail: { code: "queue_saturated" }, retryAfterSeconds: 30 }),
    );
    const dialog = openDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "Re-ingest" }));

    await waitFor(() => expect(within(dialog).getByText(/The ingestion queue is full/)).toBeInTheDocument());
    expect(within(dialog).getByText("30 s")).toBeInTheDocument();
  });

  it("offers the allowed stages on 422 replay_unsupported", async () => {
    mocked.mockRejectedValueOnce(
      new HttpError(422, [{ message: "x" }], { detail: { code: "replay_unsupported", reason: "no metagen here", allowed: ["chunk"] } }),
    );
    const dialog = openDialog();
    fireEvent.change(within(dialog).getByLabelText("Replay from stage"), { target: { value: "metagen_document" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Re-ingest" }));

    await waitFor(() => expect(within(dialog).getByText("no metagen here")).toBeInTheDocument());
    fireEvent.click(within(dialog).getByRole("button", { name: "chunk" }));
    expect((within(dialog).getByLabelText("Replay from stage") as HTMLSelectElement).value).toBe("chunk");
  });
});
