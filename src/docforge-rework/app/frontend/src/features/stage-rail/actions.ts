// ====== Code Summary ======
// The action surface the page hands to every card — one typed façade over the server-side
// `/apply` API, so components never build a StageAction themselves and every mutation funnels
// through the same serialized round-trip (see StageRailPage).

import type { ChainStep, StackMethod } from "../../api/types";

export interface StageRailActions {
  enableStage: (stageKey: string) => void;
  disableStage: (stageKey: string) => void;
  setProvider: (stageKey: string, kind: string) => void;
  /** Typing a stage's own config field (render, enrich, metagen chunk/document, parse, chunk, embed) — debounced. */
  setConfig: (stageKey: string, field: string, value: unknown) => void;
  /** Discrete stack edit (add/remove/reorder) — sent immediately, no debounce. */
  setStackSteps: (stageKey: string, steps: StackMethod[]) => void;
  /** Typing a stack method's own config field (contextualize) — debounced. */
  setStackMethodConfig: (stageKey: string, index: number, field: string, value: unknown) => void;
  /** Discrete chain edit (add/remove/reorder a fallback step) — sent immediately, no debounce. */
  setChainSteps: (stageKey: string, slot: string, steps: ChainStep[]) => void;
  /** Typing a chain step's own config field — debounced. */
  setChainStepConfig: (stageKey: string, slot: string, index: number, field: string, value: unknown) => void;
  /** Typing a chain step's escalation threshold — debounced. */
  setChainStepScoreBelow: (stageKey: string, slot: string, index: number, value: number | null) => void;
}
