// ====== Code Summary ======
// Render smoke-test for CorpusPage's loading→loaded transition — the same class of bug the
// CollectionOverview/Sidebar smoke-gates exist to catch, but for the corpus grid specifically: it
// mounts through `@tanstack/react-virtual` + a live `ResizeObserver` (see CorpusTable), neither of
// which jsdom implements, so a hooks-order or virtualization crash here would otherwise only surface
// in a real browser. Covers both loaded shapes — an empty collection (the "No documents yet" hero,
// which never mounts CorpusTable at all) and a populated one (the actual virtualized grid, with its
// sticky "__actions" column and per-row re-ingest/delete controls) — plus the always-visible
// "Filters" toggle that sits in the toolbar regardless of which branch is showing.

import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "../../api/collections";
import type { DocumentGridRow, DocumentQueryResponse } from "../../api/corpus";
import { ToastProvider } from "../../shell/toast";
import { CorpusPage } from "./CorpusPage";

// CorpusRowActions (rendered per row once documents exist) calls `useToast()` unconditionally, so
// every render needs a real <ToastProvider> up the tree — same requirement as CollectionOverview's.
function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  getCollection: vi.fn(),
}));

vi.mock("../../api/corpus", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/corpus")>()),
  queryDocuments: vi.fn(),
}));

const { getCollection } = await import("../../api/collections");
const { queryDocuments } = await import("../../api/corpus");

// `@tanstack/react-virtual` only renders a row window once its scroll container reports a nonzero
// size — it reads `offsetWidth`/`offsetHeight` synchronously at mount (see `virtual-core`'s
// `getRect`), independently of the `ResizeObserver` stub in test/setup.ts (that stub only prevents
// the constructor-missing throw; jsdom never actually lays anything out, so both offsets stay 0
// without this). Scoped to this file only, matching this file's own jsdom instance.
Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 1200 });

const baseCollection: Collection = {
  id: "col-1",
  name: "Test Collection",
  supported_formats: ["pdf"],
  tags: [],
  max_file_size_bytes: 10_000_000,
  job_timeout_seconds: null,
  needs_reindex: false,
  created_at: "2026-01-01T00:00:00Z",
  pipeline: {},
  search: {},
  fields: [],
  estimate_overrides: null,
};

function documentRowFixture(id: string): DocumentGridRow {
  return {
    id,
    filename: `${id}.pdf`,
    format: "pdf",
    status: "done",
    page_count: 3,
    file_size: 1234,
    created_at: "2026-01-01T00:00:00Z",
    title: `Document ${id}`,
    language: "en",
    enabled: true,
    metadata: {},
  };
}

function queryResponse(rows: DocumentGridRow[]): DocumentQueryResponse {
  return { total: rows.length, limit: 100, offset: 0, rows };
}

describe("CorpusPage — loading to loaded transition", () => {
  it("mounts through loading -> loaded with 0 documents without throwing", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);
    vi.mocked(queryDocuments).mockResolvedValue(queryResponse([]));

    expect(() =>
      renderWithProviders(<CorpusPage collectionId="col-1" onNavigate={vi.fn()} />),
    ).not.toThrow();

    // Before `getCollection` resolves, CorpusPage is still in its "loading collection" branch.
    expect(screen.getByText("loading collection…")).toBeInTheDocument();

    // Past the transition: no filter is active and the query came back empty — the first-run
    // empty-collection hero renders (CorpusTable itself never mounts on this branch).
    await waitFor(() => expect(screen.getByText("No documents yet")).toBeInTheDocument());
    expect(screen.queryByText("loading collection…")).not.toBeInTheDocument();

    // The "Filters" toolbar toggle is chrome, not grid content — present regardless of which
    // content branch is showing.
    expect(screen.getByRole("button", { name: "Toggle column filters" })).toHaveTextContent("Filters");
  });

  it("mounts through loading -> loaded with N documents without throwing, rendering the virtualized grid", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);
    vi.mocked(queryDocuments).mockResolvedValue(queryResponse([documentRowFixture("doc-1"), documentRowFixture("doc-2")]));

    expect(() =>
      renderWithProviders(<CorpusPage collectionId="col-1" onNavigate={vi.fn()} />),
    ).not.toThrow();

    expect(screen.getByText("loading collection…")).toBeInTheDocument();

    // Past the transition: the populated grid renders (not the loading state or the empty hero) —
    // this is the branch that exercises CorpusTable's virtualizer + ResizeObserver-driven sizing.
    await waitFor(() => expect(screen.getByText("doc-1.pdf")).toBeInTheDocument());
    expect(screen.queryByText("loading collection…")).not.toBeInTheDocument();
    expect(screen.queryByText("No documents yet")).not.toBeInTheDocument();
    expect(screen.getByText("doc-2.pdf")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Toggle column filters" })).toHaveTextContent("Filters");

    // The sticky "__actions" column's per-row controls (CorpusRowActions) rendered for both rows —
    // the grid didn't silently drop rows or crop the pinned trailing column.
    const reingestButtons = screen.getAllByLabelText("Re-ingest this document");
    expect(reingestButtons).toHaveLength(2);
    const deleteButtons = screen.getAllByText("delete");
    expect(deleteButtons).toHaveLength(2);
    // Each action pair lives in the row's own "__actions" cell, confirming the column is wired to
    // the row rather than floating detached in the header.
    const actionsCell = reingestButtons[0].closest("td");
    expect(actionsCell).not.toBeNull();
    expect(within(actionsCell as HTMLElement).getByText("delete")).toBeInTheDocument();
  });
});
