// ====== Code Summary ======
// End-to-end through the rail hook: turning a slot off POSTs `set_provider` with `kind: null`, and the
// server's refusal notice is rendered; a slot config edit POSTs a slot-scoped `merge` set_config.

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GroupBlob } from "../../../api/types";
import { ToastProvider } from "../../../shell/toast";
import { StageRailPage } from "../StageRailPage";
import { makeEmbedStage } from "./embedSlotsFixture";

vi.mock("../../../api/capabilities", () => ({ getCapabilities: vi.fn().mockResolvedValue({ capabilities: {} }) }));
vi.mock("../../../api/pipelines", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/pipelines")>()),
  listPipelineDesigns: vi.fn(),
  getDesign: vi.fn(),
  viewStages: vi.fn(),
  applyStageAction: vi.fn(),
}));
const { listPipelineDesigns, getDesign, viewStages, applyStageAction } = await import("../../../api/pipelines");

const blob: GroupBlob = { node_type: "group", id: "root", nodes: [], transitions: [], bindings: {} };

async function mountRail() {
  vi.mocked(listPipelineDesigns).mockResolvedValue({
    pipelines: [{
      key: "ingest", title: "Ingest", description: "", design_url: "/d", inspect_url: "/i", edit_url: "/e",
      stages_view_url: "/v", stages_apply_url: "/a",
    }],
  });
  vi.mocked(getDesign).mockResolvedValue({ palette: { families: [] }, blob, issues: [] });
  vi.mocked(viewStages).mockResolvedValue({ stages: [makeEmbedStage()], valid: true, issues: [], build_error: null });
  render(<ToastProvider><StageRailPage /></ToastProvider>);
  await screen.findByLabelText("Dense provider provider");
}

describe("embed slots in the stage rail", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends kind null on Turn off and renders the server notice", async () => {
    await mountRail();
    vi.mocked(applyStageAction).mockResolvedValue({
      blob, stages: [makeEmbedStage()], valid: true, issues: [], build_error: null,
      notices: ["Cannot turn off the sparse slot: the dense slot is already off."],
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Turn off" })[1]);
    await waitFor(() => expect(applyStageAction).toHaveBeenCalledWith(
      "/a", blob, { action: "set_provider", stage: "embed", slot: "sparse", kind: null },
    ));
    expect(await screen.findByText(/dense slot is already off/)).toBeInTheDocument();
  });

  it("sends a slot-scoped merge set_config after the debounce", async () => {
    await mountRail();
    vi.mocked(applyStageAction).mockResolvedValue({
      blob, stages: [makeEmbedStage()], valid: true, issues: [], build_error: null, notices: [],
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const [denseUrl] = screen.getAllByDisplayValue("http://bge_server:80");
    fireEvent.change(denseUrl, { target: { value: "http://other:80" } });
    await act(async () => { vi.advanceTimersByTime(500); });
    vi.useRealTimers();
    await waitFor(() => expect(applyStageAction).toHaveBeenCalledWith(
      "/a", blob,
      { action: "set_config", stage: "embed", slot: "dense", config: { base_url: "http://other:80" }, mode: "merge" },

    ));
  });
});
