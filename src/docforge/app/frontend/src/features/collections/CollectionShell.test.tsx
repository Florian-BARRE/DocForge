// ====== Code Summary ======
// Render smoke-test for the top-level "Ingestion" section tab (promoted out of Corpus's own
// sub-tabs — naive-user testing found the ingest stage-rail undiscoverable buried under
// Corpus → "Ingestion pipeline"; round-4 audit renamed the bare "Pipeline" label to "Ingestion"
// once a second, search-side pipeline made "Pipeline" ambiguous). Asserts the level-1 nav lists
// Ingestion alongside Overview/Documents/Search/Jobs, and that its own sub-tabs no longer
// duplicate it.

import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "../../api/collections";
import { ToastProvider } from "../../shell/toast";
import { CollectionShell } from "./CollectionShell";

// `useDeleteCollection` (called unconditionally by CollectionShell) calls `useToast`, which throws
// outside a <ToastProvider> by design (see shell/toast.tsx) — same wrapper CollectionOverview's own
// render smoke-test uses.
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

describe("CollectionShell — Ingestion top-level tab", () => {
  it("lists Ingestion as its own level-1 section, not a Documents sub-tab", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);

    renderWithProviders(
      <CollectionShell collectionId="col-1" active="pipeline" onNavigate={vi.fn()}>
        <div>pipeline content</div>
      </CollectionShell>,
    );

    await waitFor(() => expect(screen.getByRole("tablist", { name: "Collection sections" })).toBeInTheDocument());

    const sectionTabs = screen.getByRole("tablist", { name: "Collection sections" });
    expect(sectionTabs).toHaveTextContent("Ingestion");
    expect(sectionTabs).toHaveTextContent("Documents");

    // The level-1 strip alone (Ingestion active, Pipeline has no sub-tabs) must not carry a stale
    // "Ingestion pipeline" sub-tab entry.
    expect(screen.queryByRole("tab", { name: "Ingestion pipeline" })).not.toBeInTheDocument();
  });

  it("Documents section keeps only Metadata as a sub-tab (no redundant 'Documents' sub-tab)", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);

    renderWithProviders(
      <CollectionShell collectionId="col-1" active="documents" onNavigate={vi.fn()}>
        <div>documents content</div>
      </CollectionShell>,
    );

    await waitFor(() => expect(screen.getByRole("tablist", { name: "Documents views" })).toBeInTheDocument());
    const subTabs = screen.getByRole("tablist", { name: "Documents views" });
    expect(within(subTabs).getByRole("tab", { name: "Metadata" })).toBeInTheDocument();
    expect(within(subTabs).queryByRole("tab", { name: "Documents" })).not.toBeInTheDocument();
  });

  it("Search section keeps only 'Pipeline de recherche' as a sub-tab (no redundant 'Search' sub-tab)", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);

    renderWithProviders(
      <CollectionShell collectionId="col-1" active="search" onNavigate={vi.fn()}>
        <div>search content</div>
      </CollectionShell>,
    );

    await waitFor(() => expect(screen.getByRole("tablist", { name: "Search views" })).toBeInTheDocument());
    const subTabs = screen.getByRole("tablist", { name: "Search views" });
    expect(within(subTabs).getByRole("tab", { name: "Pipeline de recherche" })).toBeInTheDocument();
    expect(within(subTabs).queryByRole("tab", { name: "Search" })).not.toBeInTheDocument();
  });
});
