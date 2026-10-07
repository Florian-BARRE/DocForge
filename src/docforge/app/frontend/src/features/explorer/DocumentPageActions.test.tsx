// ====== Code Summary ======
// The document page's Re-ingest sends the chosen replay stage, and a 422 replay_unsupported shows
// the server's reason with the allowed stages.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "../../api/http";
import { ToastProvider } from "../../shell/toast";
import { DocumentPageActions } from "./DocumentPageActions";

vi.mock("../../api/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/documents")>()),
  reingestDocument: vi.fn(),
  setDocumentEnabled: vi.fn(),
}));

const { reingestDocument } = await import("../../api/documents");
const mocked = vi.mocked(reingestDocument);

function renderActions() {
  render(
    <ToastProvider>
      <DocumentPageActions documentId="d1" collectionId="c1" enabled onEnabledChanged={vi.fn()} onNavigate={vi.fn()} />
    </ToastProvider>,
  );
}

describe("DocumentPageActions — replay from stage", () => {
  beforeEach(() => mocked.mockReset());

  it("renders the stage select defaulting to a full re-ingest and sends replayFrom", async () => {
    mocked.mockResolvedValue({ document_id: "d1", job_id: "j1", duplicate: false });
    renderActions();
    const select = screen.getByLabelText("Replay from stage") as HTMLSelectElement;
    expect(select.value).toBe("");
    fireEvent.change(select, { target: { value: "chunk" } });
    fireEvent.click(screen.getByRole("button", { name: "Re-ingest" }));
    await waitFor(() => expect(mocked).toHaveBeenCalledWith("d1", { replayFrom: "chunk" }));
  });

  it("shows the reason and allowed stages on 422 replay_unsupported", async () => {
    mocked.mockRejectedValueOnce(
      new HttpError(422, [{ message: "x" }], { detail: { code: "replay_unsupported", reason: "never persisted", allowed: ["embed"] } }),
    );
    renderActions();
    fireEvent.click(screen.getByRole("button", { name: "Re-ingest" }));
    await waitFor(() => expect(screen.getByText("never persisted")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "embed" })).toBeInTheDocument();
  });
});
