// ====== Code Summary ======
// The editable assumption-override fields — a data-driven descriptor list so
// EstimateAssumptionsForm stays one small render loop instead of 12 hand-written rows.
// `target_chunk_tokens`/`chunk_overlap_ratio` are deliberately absent: the backend's
// EstimateOverrideMerger always recomputes them from the collection's ACTUAL chunker config on top
// of any override, so exposing them here would offer a knob with zero real effect.

import type { AssumptionOverrides } from "../../../api/collections";

export type AssumptionKey = keyof AssumptionOverrides;

export interface AssumptionField {
  key: AssumptionKey;
  label: string;
  hint: string;
  suffix?: string;
  min?: number;
  max?: number;
}

export const ASSUMPTION_FIELDS: AssumptionField[] = [
  { key: "tokens_per_page", label: "Text tokens per page", hint: "Assumed body-text tokens on a typical page.", suffix: "tokens", min: 0 },
  { key: "bytes_per_token", label: "Bytes per token", hint: "Assumed bytes per token for text-native formats.", suffix: "bytes", min: 0 },
  { key: "bytes_per_page", label: "Bytes per page (unknown page count)", hint: "Fallback size assumption for binary documents with no known page count.", suffix: "bytes", min: 0 },
  { key: "images_per_page", label: "Images per page", hint: "Assumed figures/images per page — drives the enrich (OCR/VLM) volume.", min: 0 },
  { key: "scanned_page_ratio", label: "Scanned page ratio", hint: "Fraction of pages assumed to need paid OCR (0 = none, 1 = all).", min: 0, max: 1 },
  { key: "llm_prompt_overhead_tokens", label: "LLM prompt overhead", hint: "Prompt tokens per contextualize call, beyond the chunk body itself.", suffix: "tokens", min: 0 },
  { key: "llm_output_tokens", label: "LLM output tokens", hint: "Completion tokens per contextualize call.", suffix: "tokens", min: 0 },
  { key: "metagen_doc_context_tokens", label: "Metadata generation context", hint: "Prompt tokens fed per document-scope metadata-generation call.", suffix: "tokens", min: 0 },
  { key: "metagen_output_tokens_per_field", label: "Metadata generation output", hint: "Completion tokens per generated metadata field.", suffix: "tokens", min: 0 },
  { key: "vlm_prompt_tokens_per_image", label: "VLM prompt tokens per image", hint: "Prompt tokens per vision-model call (image + instruction).", suffix: "tokens", min: 0 },
  { key: "vlm_output_tokens", label: "VLM output tokens", hint: "Completion tokens per vision-model caption call.", suffix: "tokens", min: 0 },
  { key: "embed_dense_dims", label: "Dense vector dimensions", hint: "Used only to project the storage footprint, not the price.", suffix: "dims", min: 1 },
];
