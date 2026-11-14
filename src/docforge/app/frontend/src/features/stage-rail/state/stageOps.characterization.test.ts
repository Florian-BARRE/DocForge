// ====== Code Summary ======
// Characterization (safety net) of stage-rail/state/stageOps.ts: records TODAY's pure helpers over
// the StageView[] the rail renders — the local mirrors (typing) and the StageAction builders
// (the exact `/apply` payloads) — as input -> output goldens, so the stage-rail split (R-33) cannot
// change what is sent to the backend. Pins immutability, the full-replacement rule, the `slot: null`
// rule for stage-owned chains, and the merge/`null`-delete rule for provider slot configs.

// ====== Third-Party Library Imports ======
import { describe, expect, it } from "vitest";

// ====== Local Project Imports ======
import type { ChainStep, StackMethod, StageView } from "../../../api/types";
import {
  buildSetChainAction,
  buildSetConfigAction,
  buildSetSlotConfigAction,
  buildSetStackAction,
  buildSetStackMethodChainAction,
  findStage,
  localSetChainStepConfig,
  localSetChainStepScoreBelow,
  localSetSlotConfig,
  localSetStackMethodChainStepConfig,
  localSetStackMethodConfig,
  localSetStageConfig,
} from "./stageOps";

const step = (kind: string, config: Record<string, unknown> = {}, score_below: number | null = null): ChainStep => ({
  kind,
  config,
  score_below,
});

function stage(key: string, overrides: Partial<StageView> = {}): StageView {
  return {
    key,
    title: key,
    description: "",
    kind: "fixed",
    enabled: true,
    removable: false,
    family: null,
    provider: null,
    available: [],
    config: null,
    chains: [],
    stack: [],
    slots: [],
    requires: [],
    notes: null,
    ...overrides,
  };
}

function stages(): StageView[] {
  return [
    stage("parse", {
      kind: "provider",
      provider: "docling",
      config: { ocr: true },
      chains: [
        { slot: "parse", title: "Parse", description: "", family: "parser", available: ["docling", "mineru"], steps: [step("docling", { a: 1 }), step("mineru", {}, 0.4)] },
      ],
    }),
    stage("enrich", {
      kind: "toggle",
      chains: [
        { slot: "scanned_text_ocr", title: "OCR", description: "", family: "ocr", available: [], steps: [step("paddle"), step("vlm", { m: "x" })] },
      ],
    }),
    stage("embed", {
      kind: "provider",
      slots: [
        { slot: "dense", title: "Dense", description: "", provider: "bge", available: ["bge"], config: { url: "u", key: "***" }, config_schemas: {} },
        { slot: "sparse", title: "Sparse", description: "", provider: null, available: [], config: null, config_schemas: {} },
      ],
    }),
    stage("contextualize", {
      kind: "stack",
      stack: [
        { kind: "doc_meta", config: { fields: ["title"] } },
        { kind: "llm", config: { model: "m" }, chain: { family: "llm", steps: [step("a", { t: 0 }), step("b")] } },
      ],
    }),
  ];
}

describe("findStage", () => {
  it("finds a stage by key and returns undefined for an unknown key", () => {
    const list = stages();
    expect(findStage(list, "embed")).toBe(list[2]);
    expect(findStage(list, "nope")).toBeUndefined();
  });
});

describe("local mirrors", () => {
  it("localSetStageConfig merges one field into the stage config only", () => {
    const before = stages();
    const after = localSetStageConfig(before, "parse", "lang", "fr");
    expect(after[0].config).toEqual({ ocr: true, lang: "fr" });
    expect(after.slice(1)).toEqual(before.slice(1));
  });

  it("localSetStageConfig treats a null config as empty", () => {
    expect(localSetStageConfig(stages(), "enrich", "x", 1)[1].config).toEqual({ x: 1 });
  });

  it("localSetStageConfig on an unknown key changes nothing", () => {
    expect(localSetStageConfig(stages(), "ghost", "x", 1)).toEqual(stages());
  });

  it("localSetSlotConfig edits one slot's config and keeps the sibling slot untouched", () => {
    const after = localSetSlotConfig(stages(), "embed", "dense", "url", "http://x");
    expect(after[2].slots[0].config).toEqual({ url: "http://x", key: "***" });
    expect(after[2].slots[1]).toEqual(stages()[2].slots[1]);
  });

  it("localSetSlotConfig starts from {} for a slot whose config is null", () => {
    expect(localSetSlotConfig(stages(), "embed", "sparse", "k", 1)[2].slots[1].config).toEqual({ k: 1 });
  });

  it("localSetStackMethodConfig edits the method at the index only", () => {
    const after = localSetStackMethodConfig(stages(), "contextualize", 0, "fields", ["title", "author"]);
    expect(after[3].stack[0].config).toEqual({ fields: ["title", "author"] });
    expect(after[3].stack[1]).toEqual(stages()[3].stack[1]);
  });

  it("localSetChainStepConfig edits one step of the matching chain slot", () => {
    const after = localSetChainStepConfig(stages(), "parse", "parse", 1, "dpi", 300);
    expect(after[0].chains[0].steps).toEqual([step("docling", { a: 1 }), step("mineru", { dpi: 300 }, 0.4)]);
  });

  it("localSetChainStepConfig on a non-matching slot changes nothing", () => {
    expect(localSetChainStepConfig(stages(), "parse", "other", 0, "x", 1)).toEqual(stages());
  });

  it("localSetChainStepScoreBelow sets and clears the threshold of one step", () => {
    const set = localSetChainStepScoreBelow(stages(), "enrich", "scanned_text_ocr", 0, 0.7);
    expect(set[1].chains[0].steps.map((s) => s.score_below)).toEqual([0.7, null]);
    const cleared = localSetChainStepScoreBelow(stages(), "parse", "parse", 1, null);
    expect(cleared[0].chains[0].steps.map((s) => s.score_below)).toEqual([null, null]);
  });

  it("localSetStackMethodChainStepConfig edits a step of the llm method's nested chain", () => {
    const after = localSetStackMethodChainStepConfig(stages(), "contextualize", 1, 1, "temp", 0.2);
    expect(after[3].stack[1].chain?.steps).toEqual([step("a", { t: 0 }), step("b", { temp: 0.2 })]);
  });

  it("localSetStackMethodChainStepConfig ignores a method without a chain", () => {
    expect(localSetStackMethodChainStepConfig(stages(), "contextualize", 0, 0, "x", 1)).toEqual(stages());
  });

  it("no mirror mutates its input", () => {
    const before = stages();
    const snapshot = structuredClone(before);
    localSetStageConfig(before, "parse", "x", 1);
    localSetSlotConfig(before, "embed", "dense", "x", 1);
    localSetStackMethodConfig(before, "contextualize", 0, "x", 1);
    localSetChainStepConfig(before, "parse", "parse", 0, "x", 1);
    localSetChainStepScoreBelow(before, "parse", "parse", 0, 1);
    localSetStackMethodChainStepConfig(before, "contextualize", 1, 0, "x", 1);
    expect(before).toEqual(snapshot);
  });
});

describe("action builders", () => {
  it("buildSetConfigAction sends the whole (mirrored) stage config as a replace", () => {
    const mirrored = localSetStageConfig(stages(), "parse", "lang", "fr");
    expect(buildSetConfigAction(mirrored, "parse")).toEqual({
      action: "set_config", stage: "parse", node: null, config: { ocr: true, lang: "fr" },
    });
  });

  it("buildSetConfigAction sends {} for a null config or an unknown stage", () => {
    expect(buildSetConfigAction(stages(), "enrich")).toEqual({ action: "set_config", stage: "enrich", node: null, config: {} });
    expect(buildSetConfigAction(stages(), "ghost")).toEqual({ action: "set_config", stage: "ghost", node: null, config: {} });
  });

  it("buildSetSlotConfigAction is a merge and turns undefined (a cleared field) into null", () => {
    expect(buildSetSlotConfigAction("embed", "dense", { url: "http://x", key: undefined, n: 0 })).toEqual({
      action: "set_config", stage: "embed", slot: "dense", config: { url: "http://x", key: null, n: 0 }, mode: "merge",
    });
  });

  it("buildSetStackAction sends the stage's whole stack, or the explicit steps when given", () => {
    expect(buildSetStackAction(stages(), "contextualize")).toEqual({
      action: "set_stack", stage: "contextualize", steps: stages()[3].stack,
    });
    const explicit: StackMethod[] = [{ kind: "breadcrumb", config: {} }];
    expect(buildSetStackAction(stages(), "contextualize", explicit)).toEqual({
      action: "set_stack", stage: "contextualize", steps: explicit,
    });
    expect(buildSetStackAction(stages(), "ghost")).toEqual({ action: "set_stack", stage: "ghost", steps: [] });
  });

  it("buildSetChainAction sends slot null for a stage-owned chain (slot == stage key)", () => {
    expect(buildSetChainAction(stages(), "parse", "parse")).toEqual({
      action: "set_chain", stage: "parse", slot: null, steps: stages()[0].chains[0].steps,
    });
  });

  it("buildSetChainAction keeps the literal slot for an enrich per-figure branch", () => {
    expect(buildSetChainAction(stages(), "enrich", "scanned_text_ocr")).toEqual({
      action: "set_chain", stage: "enrich", slot: "scanned_text_ocr", steps: stages()[1].chains[0].steps,
    });
  });

  it("buildSetChainAction replaces the steps with the given list (add / remove / reorder is the caller's list)", () => {
    const [first, second] = stages()[0].chains[0].steps;
    const reordered = [second, first];
    expect(buildSetChainAction(stages(), "parse", "parse", reordered)).toMatchObject({ steps: [second, first] });
    expect(buildSetChainAction(stages(), "parse", "parse", [first])).toMatchObject({ steps: [first] });
    expect(buildSetChainAction(stages(), "parse", "parse", [])).toMatchObject({ steps: [] });
  });

  it("buildSetChainAction sends no steps for an unknown chain slot", () => {
    expect(buildSetChainAction(stages(), "parse", "ghost")).toEqual({ action: "set_chain", stage: "parse", slot: "ghost", steps: [] });
  });

  it("buildSetStackMethodChainAction rebuilds one method's chain inside a full set_stack", () => {
    const steps = [step("z", { q: 1 })];
    const action = buildSetStackMethodChainAction(stages(), "contextualize", 1, steps);
    expect(action).toEqual({
      action: "set_stack",
      stage: "contextualize",
      steps: [
        { kind: "doc_meta", config: { fields: ["title"] } },
        { kind: "llm", config: { model: "m" }, chain: { family: "llm", steps } },
      ],
    });
  });

  it("buildSetStackMethodChainAction defaults the chain family to llm for a method without a chain", () => {
    const steps = [step("z")];
    const action = buildSetStackMethodChainAction(stages(), "contextualize", 0, steps);
    expect(action).toEqual({
      action: "set_stack",
      stage: "contextualize",
      steps: [
        { kind: "doc_meta", config: { fields: ["title"] }, chain: { family: "llm", steps } },
        stages()[3].stack[1],
      ],
    });
  });

  it("buildSetStackMethodChainAction on an unknown stage sends an empty stack", () => {
    expect(buildSetStackMethodChainAction(stages(), "ghost", 0, [])).toEqual({ action: "set_stack", stage: "ghost", steps: [] });
  });
});
