// ====== Code Summary ======
// Pure helpers over the StageView[] the rail renders — the ONE place a UI gesture is translated
// into either a LOCAL mirror (typing: config fields, chain score thresholds) or a full StageAction
// payload for `/apply`. Local-mirror-then-debounced-apply split, at the stage rail's grain:
// `set_config` / `set_chain` / `set_stack` are always FULL
// replacements, so every builder here reads the (possibly locally-mirrored) full list back out of
// `stages` before sending it — never a partial patch.
//
// `set_chain`'s slot is NOT always the chain view's own `slot`: a chain-capable provider/toggle
// stage (parse, embed, metagen chunk/document) IS the chain site, so the compiler only accepts
// that edit with `slot: null` — the view's `slot` (which equals the stage's own `key` for these)
// exists for React keys / local lookups, never as the wire slot. Only an enrich per-figure branch
// keeps its slot on the wire. `chainActionSlot` is the one place that distinction is made.

import type { ChainSpec, ChainStep, StackMethod, StageAction, StageView } from "../../../api/types";

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

function mapStackMethodChainStep(
  stages: StageView[], stageKey: string, methodIndex: number, stepIndex: number,
  mutate: (step: ChainStep) => ChainStep,
): StageView[] {
  return mapStage(stages, stageKey, (s) => ({
    ...s,
    stack: s.stack.map((method, mi) => {
      if (mi !== methodIndex || !method.chain) return method;
      return {
        ...method,
        chain: { ...method.chain, steps: method.chain.steps.map((step, si) => (si === stepIndex ? mutate(step) : step)) },
      };
    }),
  }));
}

/** Typing a step's own config field inside a stack method's nested chain (the `llm` method). */
export function localSetStackMethodChainStepConfig(
  stages: StageView[], stageKey: string, methodIndex: number, stepIndex: number, field: string, value: unknown,
): StageView[] {
  return mapStackMethodChainStep(
    stages, stageKey, methodIndex, stepIndex, (step) => ({ ...step, config: { ...step.config, [field]: value } }),
  );
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

/** The wire slot for a `set_chain` edit — `null` when the chain's view-slot equals the owning
 *  stage's own key (a stage-owned chain: parse/embed/metagen), the literal slot otherwise (an
 *  enrich per-figure branch). See the module header for why this can never be the view's `slot`
 *  verbatim. */
function chainActionSlot(stageKey: string, viewSlot: string): string | null {
  return viewSlot === stageKey ? null : viewSlot;
}

export function buildSetChainAction(stages: StageView[], stageKey: string, slot: string, steps?: ChainStep[]): StageAction {
  const stage = findStage(stages, stageKey);
  const chain = stage?.chains.find((c) => c.slot === slot);
  return {
    action: "set_chain", stage: stageKey,
    slot: chainActionSlot(stageKey, slot),
    steps: steps ?? chain?.steps ?? [],
  };
}

/** Full-stack replacement with one method's nested chain steps rebuilt (discrete edit: add/remove/
 *  reorder a step of the `llm` method's chain) — `set_stack` is the only way to reach it, the chain
 *  being part of the method rather than a separately addressed slot. */
export function buildSetStackMethodChainAction(
  stages: StageView[], stageKey: string, methodIndex: number, steps: ChainStep[],
): StageAction {
  const stage = findStage(stages, stageKey);
  const stack = stage?.stack ?? [];
  const nextStack: StackMethod[] = stack.map((method, i) => {
    if (i !== methodIndex) return method;
    const family = method.chain?.family ?? "llm";
    const chain: ChainSpec = { family, steps };
    return { ...method, chain };
  });
  return { action: "set_stack", stage: stageKey, steps: nextStack };
}
