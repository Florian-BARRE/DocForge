// ====== Code Summary ======
// Render + interaction tests for the embed stage's independent provider slots: both slots render with
// their providers, picking a kind / turning a slot off / editing a field each send the slot-scoped
// action, kinds the deployment cannot serve are greyed, and a shared bge_server shows the combined-call note.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeActions, makeEmbedStage, makeSlot } from "./embedSlotsFixture";
import { ProviderSlotsSection } from "./ProviderSlotsSection";

vi.mock("../../../api/capabilities", () => ({ getCapabilities: vi.fn() }));
const { getCapabilities } = await import("../../../api/capabilities");

beforeEach(() => {
  vi.mocked(getCapabilities).mockResolvedValue({
    capabilities: { embed_dense: ["bge_server"], embed_sparse: ["bge_server", "bm25_local"] },
  } as never);
});

describe("ProviderSlotsSection", () => {
  it("renders both slots with their providers and the combined-call note", () => {
    render(<ProviderSlotsSection stage={makeEmbedStage()} actions={makeActions()} />);
    expect(screen.getByLabelText("Dense provider provider")).toHaveValue("bge_server");
    expect(screen.getByLabelText("Sparse provider provider")).toHaveValue("bge_server");
    expect(screen.getByText("combined call (one request)")).toBeInTheDocument();
  });

  it("omits the combined-call note when the slots use different providers", () => {
    const stage = makeEmbedStage([
      makeSlot({ slot: "dense", title: "Dense provider" }),
      makeSlot({ slot: "sparse", title: "Sparse provider", provider: "bm25_local", available: ["bge_server", "bm25_local"], config: { kind: "bm25_local" } }),
    ]);
    render(<ProviderSlotsSection stage={stage} actions={makeActions()} />);
    expect(screen.queryByText("combined call (one request)")).toBeNull();
  });

  it("sends set_provider with the slot when a kind is chosen", () => {
    const actions = makeActions();
    render(<ProviderSlotsSection stage={makeEmbedStage()} actions={actions} />);
    fireEvent.change(screen.getByLabelText("Sparse provider provider"), { target: { value: "bm25_local" } });
    expect(actions.setSlotProvider).toHaveBeenCalledWith("embed", "sparse", "bm25_local");
  });

  it("sends kind null when a slot is turned off", () => {
    const actions = makeActions();
    render(<ProviderSlotsSection stage={makeEmbedStage()} actions={actions} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Turn off" })[1]);
    expect(actions.setSlotProvider).toHaveBeenCalledWith("embed", "sparse", null);
  });

  it("shows an off slot without a Turn off button or config form", () => {
    const stage = makeEmbedStage([
      makeSlot({ slot: "dense", title: "Dense provider", provider: null, config: null }),
      makeSlot({ slot: "sparse", title: "Sparse provider" }),
    ]);
    render(<ProviderSlotsSection stage={stage} actions={makeActions()} />);
    expect(screen.getAllByRole("button", { name: "Turn off" })).toHaveLength(1);
    expect(screen.getByText("off")).toBeInTheDocument();
  });

  it("routes a config field edit to the slot", () => {
    const actions = makeActions();
    render(<ProviderSlotsSection stage={makeEmbedStage()} actions={actions} />);
    const [denseUrl] = screen.getAllByDisplayValue("http://bge_server:80");
    fireEvent.change(denseUrl, { target: { value: "http://other:80" } });
    expect(actions.setSlotConfig).toHaveBeenCalledWith("embed", "dense", "base_url", "http://other:80");
  });

  it("greys out a kind this deployment cannot serve", async () => {
    render(<ProviderSlotsSection stage={makeEmbedStage()} actions={makeActions()} />);
    await waitFor(() => expect(screen.getByRole("option", { name: /openai_compatible \(unavailable here\)/ })).toBeDisabled());
    expect(screen.getAllByRole("option", { name: "bge_server" })[0]).toBeEnabled();
  });
});
