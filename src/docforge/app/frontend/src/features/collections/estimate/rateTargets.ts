// ====== Code Summary ======
// Pure derivation of the editable rate-override rows from a collection's last-run estimate stages
// PLUS whatever is already stored in its overrides — so a previously-set override for a model that
// is no longer live in the current pipeline still shows up (editable/clearable), and a freshly-seen
// model from a run with no override yet still gets a row. Split by the shape the backend's
// `RateOverrides` expects: `models` (chat/LLM/VLM, priced input+output), `embed` (single rate),
// `ocr` (single per-page rate, keyed by provider kind rather than a model id).

import type { CostEstimateStage, RateOverrides } from "../../../api/collections";

export interface RateTarget {
  /** The map key this target edits — a model id for chat/embed, a provider kind for OCR. */
  key: string;
  label: string;
}

export interface RateTargets {
  chatModels: RateTarget[];
  embedModels: RateTarget[];
  ocrProviders: RateTarget[];
}

function sortedTargets(keys: Set<string>): RateTarget[] {
  return [...keys].sort().map((key) => ({ key, label: key }));
}

/** Derives the three editable rate-row groups from the last-run stages + the stored overrides. */
export function deriveRateTargets(stages: CostEstimateStage[], overrides: RateOverrides | null | undefined): RateTargets {
  const chatKeys = new Set(Object.keys(overrides?.models ?? {}));
  const embedKeys = new Set(Object.keys(overrides?.embed ?? {}));
  const ocrKeys = new Set(Object.keys(overrides?.ocr ?? {}));

  for (const stage of stages) {
    if (stage.family === "ocr") {
      ocrKeys.add(stage.provider);
      continue;
    }
    if (!stage.model) continue;
    (stage.family === "embed" ? embedKeys : chatKeys).add(stage.model);
  }

  return {
    chatModels: sortedTargets(chatKeys),
    embedModels: sortedTargets(embedKeys),
    ocrProviders: sortedTargets(ocrKeys),
  };
}
