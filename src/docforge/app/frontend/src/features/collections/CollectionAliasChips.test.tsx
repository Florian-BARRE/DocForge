// ====== Code Summary ======
// Alias chips on the fleet card: one muted chip per alias, a chip click opens Settings ▸ Aliases
// WITHOUT firing the card's own navigate, an un-aliased collection renders nothing, and the
// aliases-by-collection hook maps GET /collection-aliases onto the right collection id.

import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "../../api/collections";
import { ToastProvider } from "../../shell/toast";
import { CollectionAliasChips } from "./CollectionAliasChips";
import { CollectionCard } from "./CollectionCard";
import { useCollectionAliases } from "./state/useCollectionAliases";

vi.mock("../../api/collectionAliases", () => ({ listCollectionAliases: vi.fn() }));
const { listCollectionAliases } = await import("../../api/collectionAliases");

const COLLECTION: Collection = {
  id: "c1", name: "Contracts", supported_formats: ["pdf"], max_file_size_bytes: 1000,
  job_timeout_seconds: null, needs_reindex: false, created_at: "2026-01-01T00:00:00Z",
  pipeline: {}, search: {}, estimate_overrides: null, trace_verbosity: "shape", title_field: null, tags: [],
  fields: [],
};

describe("collection alias chips", () => {
  it("renders nothing without aliases", () => {
    const { container } = render(<CollectionAliasChips collectionId="c1" aliases={[]} onNavigate={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the alias on the card and a click goes to Settings ▸ Aliases without opening the card", () => {
    const onNavigate = vi.fn();
    const onClick = vi.fn();
    render(
      <ToastProvider><CollectionCard
        collection={COLLECTION} health={null} healthError={null} docCount={null} jobRunning={false}
        aliases={["docs-live"]} onNavigate={onNavigate} onClick={onClick} onDeleted={vi.fn()}
      /></ToastProvider>,
    );
    fireEvent.click(screen.getByText("docs-live"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "collection-settings", collectionId: "c1", section: "aliases" });
    expect(onClick).not.toHaveBeenCalled();
  });

  it("maps GET /collection-aliases by target collection", async () => {
    const stamp = "2026-10-07T10:00:00Z";
    vi.mocked(listCollectionAliases).mockResolvedValue([
      { name: "a", collection_id: "c1", collection_name: "x", created_at: stamp, updated_at: stamp },
      { name: "b", collection_id: "c1", collection_name: "x", created_at: stamp, updated_at: stamp },
      { name: "c", collection_id: "c2", collection_name: "y", created_at: stamp, updated_at: stamp },
    ]);
    const { result } = renderHook(() => useCollectionAliases());
    await waitFor(() => expect(result.current.get("c1")).toEqual(["a", "b"]));
    expect(result.current.get("c2")).toEqual(["c"]);
  });
});
