// ====== Code Summary ======
// Regression test for the "0 issues" ingestion-editor badge (iteration-3 FIX-A): a `/stages/apply`
// result that fails to BUILD (a config value violates the node's own schema bounds) comes back with
// `issues: []` and the failure only in `build_error` — the apply handler must fold `build_error`
// into `issues` (via `issuesFromBuildError`) exactly like the initial `/stages/view` load does, so
// the badge count and `valid` never disagree.

import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { GroupBlob, Palette, StageView } from "../../../api/types";
import { ToastProvider } from "../../../shell/toast";
import { useStageRailPage } from "./useStageRailPage";

// `handleSave`'s toast calls (not exercised here, but `useToast()` is called unconditionally at the
// top of the hook) require a <ToastProvider> ancestor — same wiring `StageRailPage`'s real caller
// (CollectionShell) always provides.
function wrapper({ children }: { children: ReactNode }) {
  return <ToastProvider>{children}</ToastProvider>;
}

vi.mock("../../../api/pipelines", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/pipelines")>()),
  listPipelineDesigns: vi.fn(),
  getDesign: vi.fn(),
  viewStages: vi.fn(),
  applyStageAction: vi.fn(),
}));

const { listPipelineDesigns, getDesign, viewStages, applyStageAction } = await import("../../../api/pipelines");

const blob: GroupBlob = { node_type: "group", id: "root", nodes: [], transitions: [], bindings: {} };
const palette: Palette = { families: [] };

const stage: StageView = {
  key: "chunk", title: "Chunk", description: "Split the enriched IR into chunks.",
  kind: "provider", enabled: true, removable: false, family: "chunker", provider: "fixed_size",
  available: ["fixed_size"], config: { candidate_multiplier: 150 }, chains: [], stack: [], requires: [], notes: null,
};

describe("useStageRailPage — build_error folded into issues on /apply", () => {
  it("counts a build-failing config edit instead of reporting 0 issues while Save stays blocked", async () => {
    vi.mocked(listPipelineDesigns).mockResolvedValue({
      pipelines: [{
        key: "ingest", title: "Ingest", description: "", design_url: "/design",
        inspect_url: "/inspect", edit_url: "/edit", stages_view_url: "/view", stages_apply_url: "/apply",
      }],
    });
    vi.mocked(getDesign).mockResolvedValue({ palette, blob, issues: [] });
    vi.mocked(viewStages).mockResolvedValue({ stages: [stage], valid: true, issues: [], build_error: null });

    const { result } = renderHook(() => useStageRailPage({}), { wrapper });
    await waitFor(() => expect(result.current.stages).not.toBeNull());
    expect(result.current.valid).toBe(true);
    expect(result.current.issues).toHaveLength(0);

    // The node fails to build with the new value (e.g. candidate_multiplier > le=100): the server
    // returns valid=false + a populated build_error, and an EMPTY issues array (see StageApplyResponse
    // docstring) — the bug reproduced here is that array being taken at face value.
    vi.mocked(applyStageAction).mockResolvedValue({
      blob, stages: [stage], valid: false, issues: [], notices: [],
      build_error: "1 validation error for FixedSizeConfig\ncandidate_multiplier\n  Input should be less than or equal to 100 [type=less_than_equal]",
    });

    act(() => result.current.actions.enableStage("chunk"));
    await waitFor(() => expect(result.current.valid).toBe(false));

    expect(result.current.issues).toHaveLength(1);
    expect(result.current.issues[0].message).toContain("less than or equal to 100");
  });
});
