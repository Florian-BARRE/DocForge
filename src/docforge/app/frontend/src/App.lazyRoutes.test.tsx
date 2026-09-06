// ====== Code Summary ======
// Render smoke-test for App.tsx's lazy-route Suspense boundaries (corpus / pipeline editor /
// document explorer — see the `lazy(...)` imports + wrapping <Suspense> in App.tsx). Rather than
// mounting the whole App (which would drag in Sidebar + CollectionShell chrome fetches unrelated
// to this behavior), this test reproduces the exact same `lazy` + `<Suspense fallback=…>` pattern
// against one real lazy-wrapped page (CorpusPage) and asserts the fallback renders first, then the
// real component swaps in — the one thing code-splitting can silently break (an unresolved import
// or a missing Suspense boundary would either hang on the fallback or throw).

import { lazy, Suspense } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "./api/collections";
import type { DocumentQueryResponse } from "./api/corpus";
import { LoadingState } from "./components/LoadingState";
import { ToastProvider } from "./shell/toast";

vi.mock("./api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/collections")>()),
  getCollection: vi.fn(),
}));

vi.mock("./api/corpus", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/corpus")>()),
  queryDocuments: vi.fn(),
}));

const { getCollection } = await import("./api/collections");
const { queryDocuments } = await import("./api/corpus");

const LazyCorpusPage = lazy(() => import("./features/corpus/CorpusPage").then((m) => ({ default: m.CorpusPage })));

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

function emptyQueryResponse(): DocumentQueryResponse {
  return { total: 0, limit: 100, offset: 0, rows: [] };
}

describe("App — lazy route Suspense boundary", () => {
  it("shows the Suspense fallback, then swaps in the lazily-loaded page", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);
    vi.mocked(queryDocuments).mockResolvedValue(emptyQueryResponse());

    render(
      <ToastProvider>
        <Suspense fallback={<LoadingState label="loading corpus…" />}>
          <LazyCorpusPage collectionId="col-1" onNavigate={vi.fn()} />
        </Suspense>
      </ToastProvider>,
    );

    // The Suspense fallback is what renders before the dynamic import resolves.
    expect(screen.getByText("loading corpus…")).toBeInTheDocument();

    // Once the chunk resolves, CorpusPage itself takes over (past its own "loading collection…"
    // step) and the Suspense fallback is gone for good.
    await waitFor(() => expect(screen.getByText("No documents yet")).toBeInTheDocument());
    expect(screen.queryByText("loading corpus…")).not.toBeInTheDocument();
  });
});
