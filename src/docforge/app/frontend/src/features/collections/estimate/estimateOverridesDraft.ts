// ====== Code Summary ======
// The pure draft<->wire conversion for the rates half of the overrides editor. A model rate needs
// BOTH input and output priced together (the backend's `ModelRateOverride` has no optional half), so
// the editable draft keeps each half independently settable (`ModelRateDraft`) and only a row with
// both filled survives the trip back to `RateOverrides` — a half-filled row is silently dropped
// (equivalent to never having overridden that model), never sent as a malformed request.

import type { ModelRateOverride, RateOverrides } from "../../../api/collections";

export interface ModelRateDraft {
  input?: number;
  output?: number;
}

export interface RatesDraft {
  models: Record<string, ModelRateDraft>;
  embed: Record<string, number>;
  ocr: Record<string, number>;
}

export function emptyRatesDraft(): RatesDraft {
  return { models: {}, embed: {}, ocr: {} };
}

/** Seeds an editable draft from the collection's stored (or just-saved) rate overrides. */
export function ratesDraftFromOverrides(rates: RateOverrides | null | undefined): RatesDraft {
  const models: Record<string, ModelRateDraft> = {};
  for (const [key, rate] of Object.entries(rates?.models ?? {})) models[key] = { input: rate.input, output: rate.output };
  return { models, embed: { ...(rates?.embed ?? {}) }, ocr: { ...(rates?.ocr ?? {}) } };
}

/** Converts a draft back to the wire `RateOverrides`, or `undefined` when nothing is set (so the
 *  caller can omit the whole `rates` subtree rather than sending an empty-but-present object). */
export function ratesDraftToOverrides(draft: RatesDraft): RateOverrides | undefined {
  const models: Record<string, ModelRateOverride> = {};
  for (const [key, rate] of Object.entries(draft.models))
    if (rate.input !== undefined && rate.output !== undefined) models[key] = { input: rate.input, output: rate.output };

  const hasModels = Object.keys(models).length > 0;
  const hasEmbed = Object.keys(draft.embed).length > 0;
  const hasOcr = Object.keys(draft.ocr).length > 0;
  if (!hasModels && !hasEmbed && !hasOcr) return undefined;

  return {
    models: hasModels ? models : undefined,
    embed: hasEmbed ? draft.embed : undefined,
    ocr: hasOcr ? draft.ocr : undefined,
  };
}

/** Sets or deletes one key of a flat rate record (embed/ocr) — `undefined` removes the key entirely
 *  ("reset to default") rather than storing an `undefined` value. */
export function withRate(record: Record<string, number>, key: string, value: number | undefined): Record<string, number> {
  const next = { ...record };
  if (value === undefined) delete next[key];
  else next[key] = value;
  return next;
}
