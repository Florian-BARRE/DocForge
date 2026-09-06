// ====== Code Summary ======
// Render smoke-test for the fleet's tag filter: `availableTags` is derived from the loaded
// collections (never hardcoded), and selecting one narrows `visibleEntries` to collections
// carrying it (OR semantics against the selection) without dropping the others' data.

import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "../../../api/collections";
import { useCollectionsFleet } from "./useCollectionsFleet";

vi.mock("../../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/collections")>()),
  listCollections: vi.fn(),
  getCollectionHealth: vi.fn(() => new Promise(() => {})), // never resolves — health isn't under test
}));

vi.mock("../../../api/corpus", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/corpus")>()),
  queryDocuments: vi.fn(() => new Promise(() => {})),
}));

vi.mock("../../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/jobs")>()),
  getQueueDepth: vi.fn(() => new Promise(() => {})),
}));

const { listCollections } = await import("../../../api/collections");

function collectionFixture(id: string, name: string, tags: string[]): Collection {
  return {
    id, name, tags,
    supported_formats: ["pdf"],
    max_file_size_bytes: 10_000_000,
    job_timeout_seconds: null,
    needs_reindex: false,
    created_at: "2026-01-01T00:00:00Z",
    pipeline: {},
    search: {},
    fields: [],
    estimate_overrides: null,
  };
}

describe("useCollectionsFleet — tag filter", () => {
  it("derives availableTags from the fleet and narrows visibleEntries on selection (OR semantics)", async () => {
    vi.mocked(listCollections).mockResolvedValue([
      collectionFixture("a", "Finance Reports", ["finance", "q3"]),
      collectionFixture("b", "Legal Contracts", ["legal"]),
      collectionFixture("c", "Untagged Docs", []),
    ]);

    const { result } = renderHook(() => useCollectionsFleet());

    await waitFor(() => expect(result.current.collections).not.toBeNull());
    expect(result.current.availableTags).toEqual(["finance", "legal", "q3"]);
    expect(result.current.visibleEntries).toHaveLength(3);

    act(() => result.current.setSelectedTags(["finance"]));
    expect(result.current.visibleEntries.map((e) => e.collection.id)).toEqual(["a"]);

    // OR semantics: adding a second tag ADDS matches rather than narrowing further.
    act(() => result.current.setSelectedTags(["finance", "legal"]));
    expect(result.current.visibleEntries.map((e) => e.collection.id).sort()).toEqual(["a", "b"]);
  });

  it("matches the name search box against tags too", async () => {
    vi.mocked(listCollections).mockResolvedValue([
      collectionFixture("a", "Finance Reports", ["finance", "q3"]),
      collectionFixture("b", "Legal Contracts", ["legal"]),
    ]);

    const { result } = renderHook(() => useCollectionsFleet());
    await waitFor(() => expect(result.current.collections).not.toBeNull());

    act(() => result.current.setSearchQuery("legal"));
    expect(result.current.visibleEntries.map((e) => e.collection.id)).toEqual(["b"]);
  });
});
