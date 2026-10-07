// ====== Code Summary ======
// Render smoke-test for the Settings ▸ History section: mounts through loading → loaded, lists the
// versions with author + change summary, diffs two ticked versions, and opens the restore confirm
// with the diff vs the current head.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfigHistoryPanel } from "./ConfigHistoryPanel";

vi.mock("../../../api/configVersions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/configVersions")>()),
  listConfigVersions: vi.fn(),
  diffConfigVersions: vi.fn(),
  restoreConfigVersion: vi.fn(),
}));

const { listConfigVersions, diffConfigVersions } = await import("../../../api/configVersions");

const page = {
  collection_id: "c1",
  total: 2,
  limit: 50,
  offset: 0,
  items: [
    { version: 2, created_at: "2026-10-07T10:00:00Z", note: "stage action", author_label: "ci-bot", changes: ["pipeline:embed"] },
    { version: 1, created_at: "2026-10-06T10:00:00Z", note: "creation", author_label: null, changes: [] },
  ],
};

const diff = {
  collection_id: "c1",
  from_version: 1,
  to_version: 2,
  changes: [{ path: "/pipeline/nodes/embed/config/timeout_seconds", op: "changed" as const, before: 10, after: 20 }],
};

describe("ConfigHistoryPanel", () => {
  it("lists versions, diffs two, and opens the restore confirm", async () => {
    vi.mocked(listConfigVersions).mockResolvedValue(page);
    vi.mocked(diffConfigVersions).mockResolvedValue(diff);
    render(<ConfigHistoryPanel collectionId="c1" />);

    expect(await screen.findByText("ci-bot")).toBeInTheDocument();
    expect(screen.getByText("pipeline:embed")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Compare v2"));
    fireEvent.click(screen.getByLabelText("Compare v1"));
    expect(await screen.findByText("/pipeline/nodes/embed/config/timeout_seconds")).toBeInTheDocument();
    expect(diffConfigVersions).toHaveBeenCalledWith("c1", 1, 2);

    fireEvent.click(screen.getByText("Restore"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(diffConfigVersions).toHaveBeenLastCalledWith("c1", 2, 1);
  });
});
