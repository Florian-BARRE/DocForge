// ====== Code Summary ======
// Shared test fixture: an embed StageView with both slots on one bge_server, plus a no-op actions bag.

import { vi } from "vitest";
import type { ProviderSlotView, StageView } from "../../../api/types";
import type { StageRailActions } from "../actions";

const bgeSchema = {
  properties: {
    kind: { type: "string" },
    base_url: { type: "string", title: "Base URL" },
    api_key: { type: "string", title: "API key" },
    model: { type: "string", title: "Model" },
  },
};

export function makeSlot(overrides: Partial<ProviderSlotView> & Pick<ProviderSlotView, "slot" | "title">): ProviderSlotView {
  return {
    description: "slot description",
    provider: "bge_server",
    available: ["bge_server", "openai_compatible"],
    config: { kind: "bge_server", base_url: "http://bge_server:80" },
    config_schemas: { bge_server: bgeSchema, openai_compatible: bgeSchema, bm25_local: { properties: { kind: { type: "string" }, k1: { type: "number" } } } },
    ...overrides,
  };
}

export function makeEmbedStage(slots?: ProviderSlotView[]): StageView {
  return {
    key: "embed", title: "Embed", description: "Vectorise every chunk.", kind: "provider", enabled: true,
    removable: true, family: "embed", provider: "dense_sparse", available: ["dense_sparse"], config: {},
    chains: [], stack: [], requires: [], notes: null,
    slots: slots ?? [
      makeSlot({ slot: "dense", title: "Dense provider" }),
      makeSlot({ slot: "sparse", title: "Sparse provider", available: ["bge_server", "bm25_local"] }),
    ],
  };
}

export function makeActions(): StageRailActions {
  return {
    enableStage: vi.fn(), disableStage: vi.fn(), setProvider: vi.fn(), setSlotProvider: vi.fn(), setSlotConfig: vi.fn(),
    setConfig: vi.fn(), setStackSteps: vi.fn(), setStackMethodConfig: vi.fn(), setChainSteps: vi.fn(),
    setChainStepConfig: vi.fn(), setChainStepScoreBelow: vi.fn(), setStackMethodChainSteps: vi.fn(),
    setStackMethodChainStepConfig: vi.fn(),
  };
}
