// ====== Code Summary ======
// Render smoke-test for the Settings ▸ Aliases section: mounts through loading → loaded, separates the
// aliases pointing here from the others, and only switches an alias after the confirm dialog
// (PUT /collection-aliases/{name} with this collection's id).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../../shell/toast";
import { AliasesPanel } from "./AliasesPanel";

vi.mock("../../../api/collectionAliases", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/collectionAliases")>()),
  listCollectionAliases: vi.fn(),
  setCollectionAlias: vi.fn(),
}));

const { listCollectionAliases, setCollectionAlias } = await import("../../../api/collectionAliases");

const stamp = "2026-10-07T10:00:00Z";
const aliases = [
  { name: "docs-live", collection_id: "c1", collection_name: "docs-blue", created_at: stamp, updated_at: stamp },
  { name: "contracts", collection_id: "c2", collection_name: "contracts-v1", created_at: stamp, updated_at: stamp },
];

function renderPanel() {
  render(
    <ToastProvider>
      <AliasesPanel collectionId="c1" collectionName="docs-blue" />
    </ToastProvider>,
  );
}

describe("AliasesPanel", () => {
  it("lists the aliases and switches one only after the confirm", async () => {
    vi.mocked(listCollectionAliases).mockResolvedValue(aliases);
    vi.mocked(setCollectionAlias).mockResolvedValue({ ...aliases[1], collection_id: "c1", created: false });
    renderPanel();

    expect(screen.getByText("loading aliases…")).toBeInTheDocument();
    expect(await screen.findByTestId("alias-here")).toHaveTextContent("docs-live");
    expect(screen.getByText("contracts")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Switch alias here" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("contracts-v1");
    expect(setCollectionAlias).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole("button", { name: "Switch alias here" }).at(-1)!);
    await waitFor(() => expect(setCollectionAlias).toHaveBeenCalledWith("contracts", "c1"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("renders the empty state when no alias exists", async () => {
    vi.mocked(listCollectionAliases).mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByText("No alias points at this collection.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Point alias here" })).toBeDisabled();
  });
});
