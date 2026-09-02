// ====== Code Summary ======
// Humanizes a provider's raw graph vocabulary (`family`/`kind`, e.g. "vlm"/"openai_compatible") into
// a readable board label ("VLM · OpenAI-compatible") — the health board is the last surface that
// still leaked engine internals (node kinds, bare ids) straight to the screen. Any kind/family absent
// from these maps falls back to the raw string, so a new provider node never crashes the board; it
// just reads a little less polished until this file is updated.

/** Family (step-role) → short display label, mirroring `NodeRegistry`'s family vocabulary. */
const FAMILY_LABELS: Record<string, string> = {
  intake: "Intake",
  converter: "Converter",
  parser: "Parser",
  render: "Render",
  enrich: "Enrich",
  chunker: "Chunker",
  contextualize: "Contextualize",
  metagen: "Metagen",
  embed: "Embed",
  ocr: "OCR",
  vlm: "VLM",
  llm: "LLM",
  structgen: "Structured gen",
  rerank: "Rerank",
};

/** Provider kind → display label, mirroring every `KIND` constant that ships a `preflight()`. */
const KIND_LABELS: Record<string, string> = {
  docling: "Docling",
  granite_docling: "Granite Docling",
  pp_structure: "PP-StructureV3",
  rapidocr: "RapidOCR",
  paddle: "PaddleOCR",
  mistral: "Mistral",
  openai_compatible: "OpenAI-compatible",
  bge_server: "BGE-M3",
  gotenberg: "Gotenberg",
  cross_encoder: "Cross-encoder",
};

/**
 * Humanize one provider row's step + kind into a single readable label.
 *
 * @param family - The node's family (step role), e.g. "vlm".
 * @param kind - The node's kind (provider), e.g. "openai_compatible".
 * @returns A "Step · Provider" label, falling back to the raw token for anything unmapped.
 */
export function humanizeProviderLabel(family: string, kind: string): string {
  const familyLabel = FAMILY_LABELS[family] ?? family;
  const kindLabel = KIND_LABELS[kind] ?? kind;
  return `${familyLabel} · ${kindLabel}`;
}
