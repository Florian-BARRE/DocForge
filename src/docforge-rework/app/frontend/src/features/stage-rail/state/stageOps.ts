// ====== Code Summary ======
// Pure helpers over the StageView[] the rail renders — the ONE place a UI gesture is translated
// into either a LOCAL mirror (typing: config fields, chain score thresholds) or a full StageAction
// payload for `/apply`. Local-mirror-then-debounced-apply split, at the stage rail's grain:
// `set_config` / `set_chain` / `set_stack` are always FULL
// replacements, so every builder here reads the (possibly locally-mirrored) full list back out of
// `stages` before sending it — never a partial patch.

import type { ChainStep, StackMethod, StageAction, StageView } from "../../../api/types";

export function findStage(stages: StageView[], key: string): StageView | undefined {
  return stages.find((s) => s.key === key);
}

function mapStage(stages: StageView[], key: string, mutate: (s: StageView) => StageView): StageView[] {
  return stages.map((s) => (s.key === key ? mutate(s) : s));
}

// ---------- local mirrors (typing feels instant; the debounced /apply settles afterwards) ----------

export function localSetStageConfig(stages: StageView[], stageKey: string, field: string, value: unknown): StageView[] {
  return mapStage(stages, stageKey, (s) => ({ ...s, config: { ...(s.config ?? {}), [field]: value } }));
}

export function localSetStackMethodConfig(
  stages: StageView[], stageKey: string, index: number, field: string, value: unknown,
): StageView[] {
  return mapStage(stages, stageKey, (s) => ({
    ...s,
    stack: s.stack.map((method, i) => (i === index ? { ...method, config: { ...method.config, [field]: value } } : method)),
  }));
}

function mapChainStep(
  stages: StageView[], stageKey: string, slot: string, index: number, mutate: (step: ChainStep) => ChainStep,
): StageView[] {
  return mapStage(stages, stageKey, (s) => ({
    ...s,
    chains: s.chains.map((c) => (c.slot !== slot ? c : { ...c, steps: c.steps.map((step, i) => (i === index ? mutate(step) : step)) })),
  }));
}

export function localSetChainStepConfig(
  stages: StageView[], stageKey: string, slot: string, index: number, field: string, value: unknown,
): StageView[] {
  return mapChainStep(stages, stageKey, slot, index, (step) => ({ ...step, config: { ...step.config, [field]: value } }));
}

export function localSetChainStepScoreBelow(
  stages: StageView[], stageKey: string, slot: string, index: number, value: number | null,
): StageView[] {
  return mapChainStep(stages, stageKey, slot, index, (step) => ({ ...step, score_below: value }));
}

// ---------- action builders (read the settled/mirrored stage back out, whole) ----------

export function buildSetConfigAction(stages: StageView[], stageKey: string): StageAction {
  const stage = findStage(stages, stageKey);
  return { action: "set_config", stage: stageKey, node: null, config: stage?.config ?? {} };
}

export function buildSetStackAction(stages: StageView[], stageKey: string, steps?: StackMethod[]): StageAction {
  const stage = findStage(stages, stageKey);
  return { action: "set_stack", stage: stageKey, steps: steps ?? stage?.stack ?? [] };
}

export function buildSetChainAction(stages: StageView[], stageKey: string, slot: string, steps?: ChainStep[]): StageAction {
  const stage = findStage(stages, stageKey);
  const chain = stage?.chains.find((c) => c.slot === slot);
  return { action: "set_chain", stage: stageKey, slot, steps: steps ?? chain?.steps ?? [] };
}
