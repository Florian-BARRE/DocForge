// ====== Code Summary ======
// The action façade every stage-rail card uses, as a pure factory: each entry is a thin adapter that
// translates ONE gesture into ONE `/apply` action — discrete edits go straight through `applyAction`,
// typed edits go through the local-mirror-then-debounce path. No React; the hook
// (useStageRailPage) supplies the transport and memoises the result.

import type { StageAction, StageView } from "../../../api/types";
import type { StageRailActions } from "../actions";
import {
  buildSetChainAction, buildSetConfigAction, buildSetStackAction, buildSetStackMethodChainAction,
  localSetChainStepConfig, localSetChainStepScoreBelow, localSetStackMethodChainStepConfig,
  localSetStackMethodConfig, localSetStageConfig,
} from "./stageOps";

export interface StageRailActionDeps {
  /** Funnel one action through the serialized `/apply` queue. */
  applyAction: (action: StageAction) => void;
  /** Mutate the local `stages` mirror now, then `/apply` the action built from the settled stages. */
  applyLocalThenDebounced: (
    mutateLocally: (s: StageView[]) => StageView[],
    buildAction: (s: StageView[]) => StageAction,
  ) => void;
  /** Slot config edits (merge-patch accumulated across one debounce window). */
  setSlotConfig: StageRailActions["setSlotConfig"];
  /** The freshest stage views (read at call time, never captured). */
  currentStages: () => StageView[];
}

export function buildStageRailActions(deps: StageRailActionDeps): StageRailActions {
  const { applyAction, applyLocalThenDebounced, setSlotConfig, currentStages } = deps;
  return {
    enableStage: (stageKey) => applyAction({ action: "enable_stage", stage: stageKey }),
    disableStage: (stageKey) => applyAction({ action: "disable_stage", stage: stageKey }),
    setProvider: (stageKey, kind) => applyAction({ action: "set_provider", stage: stageKey, kind }),
    setSlotProvider: (stageKey, slot, kind) => applyAction({ action: "set_provider", stage: stageKey, slot, kind }),
    setSlotConfig,
    setConfig: (stageKey, field, value) => applyLocalThenDebounced(
      (s) => localSetStageConfig(s, stageKey, field, value),
      (s) => buildSetConfigAction(s, stageKey),
    ),
    setStackSteps: (stageKey, steps) => applyAction(buildSetStackAction(currentStages(), stageKey, steps)),
    setStackMethodConfig: (stageKey, index, field, value) => applyLocalThenDebounced(
      (s) => localSetStackMethodConfig(s, stageKey, index, field, value),
      (s) => buildSetStackAction(s, stageKey),
    ),
    setChainSteps: (stageKey, slot, steps) => applyAction(buildSetChainAction(currentStages(), stageKey, slot, steps)),
    setChainStepConfig: (stageKey, slot, index, field, value) => applyLocalThenDebounced(
      (s) => localSetChainStepConfig(s, stageKey, slot, index, field, value),
      (s) => buildSetChainAction(s, stageKey, slot),
    ),
    setChainStepScoreBelow: (stageKey, slot, index, value) => applyLocalThenDebounced(
      (s) => localSetChainStepScoreBelow(s, stageKey, slot, index, value),
      (s) => buildSetChainAction(s, stageKey, slot),
    ),
    setStackMethodChainSteps: (stageKey, methodIndex, steps) =>
      applyAction(buildSetStackMethodChainAction(currentStages(), stageKey, methodIndex, steps)),
    setStackMethodChainStepConfig: (stageKey, methodIndex, stepIndex, field, value) => applyLocalThenDebounced(
      (s) => localSetStackMethodChainStepConfig(s, stageKey, methodIndex, stepIndex, field, value),
      (s) => buildSetStackMethodChainAction(
        s, stageKey, methodIndex,
        s.find((st) => st.key === stageKey)?.stack[methodIndex]?.chain?.steps ?? [],
      ),
    ),
  };
}
