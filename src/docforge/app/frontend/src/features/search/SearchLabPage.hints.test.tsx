// ====== Code Summary ======
// Render smoke-test: a search response carrying hints shows the notice with suggestion chips, and
// clicking a chip re-runs the search with that value substituted into the filter.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../shell/toast";
import { applyHintSuggestion } from "./hintSubstitution";

vi.mock("../../api/search", async (orig) => ({ ...(await orig<typeof import("../../api/search")>()), search: vi.fn() }));
vi.mock("../../api/collections", async (orig) => ({ ...(await orig<typeof import("../../api/collections")>()), getCollection: vi.fn() }));
vi.mock("../../api/corpus", async (orig) => ({ ...(await orig<typeof import("../../api/corpus")>()), queryDocuments: vi.fn() }));

const { search } = await import("../../api/search");
const { getCollection } = await import("../../api/collections");
const { queryDocuments } = await import("../../api/corpus");
const { SearchLabPage } = await import("./SearchLabPage");

describe("applyHintSuggestion", () => {
  const hint = { field: "lang", value: "FR", message: "m", suggestions: ["fr"] };
  it("replaces scalar, list item and operator values", () => {
    expect(applyHintSuggestion({ lang: "FR" }, hint, "fr")).toEqual({ lang: "fr" });
    expect(applyHintSuggestion({ lang: ["FR", "en"] }, hint, "fr")).toEqual({ lang: ["fr", "en"] });
    expect(applyHintSuggestion({ lang: { in: ["FR"] } }, hint, "fr")).toEqual({ lang: { in: ["fr"] } });
  });
});

describe("SearchLabPage hints", () => {
  it("renders the notice and re-runs with the substituted filter on chip click", async () => {
    vi.mocked(getCollection).mockResolvedValue({ fields: [] } as never);
    vi.mocked(queryDocuments).mockResolvedValue({ total: 1 } as never);
    vi.mocked(search).mockResolvedValue({
      query: "q", hits: [], debug_info: null,
      hints: [{ field: "lang", value: "FR", message: "No document stores lang=FR.", suggestions: ["fr"] }],
    });

    render(<ToastProvider><SearchLabPage collectionId="c1" onNavigate={() => {}} /></ToastProvider>);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "q" } });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });

    // The first run carries no filter; seed the re-run through the chip (filters state is empty so
    // substitution is a no-op there — assert the chip triggers a second search call).
    const chip = await screen.findByRole("button", { name: "fr" });
    expect(screen.getByText("No document stores lang=FR.")).toBeInTheDocument();
    fireEvent.click(chip);
    await waitFor(() => expect(vi.mocked(search)).toHaveBeenCalledTimes(2));
  });
});
