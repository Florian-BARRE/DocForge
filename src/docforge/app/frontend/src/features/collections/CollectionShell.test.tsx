// ====== Code Summary ======
// Render smoke-test for the redesigned CollectionShell — now a CONTENT FRAME (the persistent left
// rail owns the in-collection nav since the IA redesign, so the shell no longer renders a section /
// sub-tab strip). Asserts: the header chrome mounts (breadcrumb "Collections" + the collection name);
// the ONLY remaining in-content sub-nav — the Ingestion | Search bar — shows exactly when a
// `pipelineStage` is set and is absent otherwise; and the old French "Pipeline de recherche" sub-tab
// is gone (the two editors are now equal-depth English tabs). Export/Delete no longer live in this
// shell (moved to Settings ▸ Transfer/▸ Danger zone) — kept wrapped in <ToastProvider> regardless,
// matching CollectionOverview's own smoke-test harness, since a nested page (e.g. UploadPanel once
// shown) may still call `useToast`.

import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "../../api/collections";
import { ToastProvider } from "../../shell/toast";
import { CollectionShell } from "./CollectionShell";

function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  getCollection: vi.fn(),
}));

const { getCollection } = await import("../../api/collections");

const baseCollection: Collection = {
  id: "col-1",
  name: "Test Collection",
  supported_formats: ["pdf"],
  max_file_size_bytes: 10_000_000,
  job_timeout_seconds: null,
  needs_reindex: false,
  created_at: "2026-01-01T00:00:00Z",
  pipeline: {},
  search: {},
  fields: [],
  estimate_overrides: null,
  trace_verbosity: "shape",
  tags: [],
};

describe("CollectionShell — content frame", () => {
  it("renders the header chrome and no section tab strip (the rail owns nav now)", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);
    renderWithProviders(
      <CollectionShell collectionId="col-1" onNavigate={vi.fn()}>
        <div>overview content</div>
      </CollectionShell>,
    );
    // The name shows in both the breadcrumb's last segment and the title, so match ≥1.
    await waitFor(() => expect(screen.getAllByText("Test Collection").length).toBeGreaterThan(0));
    // Breadcrumb back to the fleet, and the page's own content renders.
    expect(screen.getByText("Collections")).toBeInTheDocument();
    expect(screen.getByText("overview content")).toBeInTheDocument();
    // The old level-1 "Collection sections" tablist is gone.
    expect(screen.queryByRole("tablist", { name: "Collection sections" })).not.toBeInTheDocument();
    // No pipeline sub-tab bar off the Pipelines page.
    expect(screen.queryByRole("tablist", { name: "Pipeline editors" })).not.toBeInTheDocument();
  });

  it("shows the Ingestion | Search sub-tab bar on the Pipelines page (English, equal depth)", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);
    renderWithProviders(
      <CollectionShell collectionId="col-1" onNavigate={vi.fn()} pipelineStage="ingestion">
        <div>pipeline content</div>
      </CollectionShell>,
    );
    await waitFor(() => expect(screen.getByRole("tablist", { name: "Pipeline editors" })).toBeInTheDocument());
    const bar = screen.getByRole("tablist", { name: "Pipeline editors" });
    expect(within(bar).getByRole("tab", { name: "Ingestion" })).toBeInTheDocument();
    expect(within(bar).getByRole("tab", { name: "Search" })).toBeInTheDocument();
    // The French label is retired.
    expect(screen.queryByText("Pipeline de recherche")).not.toBeInTheDocument();
  });
});
