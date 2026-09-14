// ====== Code Summary ======
// Humanizes a job event/stage's raw graph node id (the engine's internal wiring name, e.g.
// "meta_doc_loop", "pdf_probe") into a short readable label for the job timeline. Curated for every
// node id the ingest SegmentBuilder emits (shared_libs/pipelines/ingest/stages/segments.py) plus the
// parse/embed fallback-chain step ids ("parse_1", "embed_2"…). The raw id itself is never discarded —
// callers keep it available as a tooltip/title, demoted behind "technical details" rather than shown
// as primary text. An id absent from this map still degrades gracefully through the snake_case →
// Title Case fallback, so a brand-new node never renders worse than today.

const STAGE_LABELS: Record<string, string> = {
  // Intake.
  probe: "Format detection",
  admit: "Admission check",
  convert: "Conversion",
  pdf_probe: "Page inspection",
  address: "Content addressing",
  // Parse / render.
  parse: "Parsing",
  figures: "Page rendering",
  // Enrich.
  extract: "Figure extraction",
  per_figure: "Figure processing",
  apply: "Enrichment merge",
  // Chunk.
  chunk: "Chunking",
  // Contextualize (stock stack node ids).
  ctx_meta: "Document metadata context",
  ctx_breadcrumb: "Heading breadcrumb context",
  ctx_sliding: "Sliding-window context",
  ctx_llm: "LLM contextualization",
  ctx_llm_loop: "LLM contextualization",
  ctx_llm_apply: "LLM contextualization merge",
  // Metadata generation (per-chunk / per-document).
  meta_chunk_prep: "Chunk metadata prep",
  meta_chunk_loop: "Chunk metadata generation",
  meta_chunk_apply: "Chunk metadata merge",
  meta_doc_prep: "Document metadata prep",
  meta_doc_loop: "Metadata generation",
  meta_doc_apply: "Metadata merge",
  // Embed / deliver.
  embed: "Embedding",
  bundle: "Processing",
};

/** A fallback-chain escalation step id ("parse_1", "embed_0") — one label per chain family, the
 *  step's raw ordinal demoted to a "(fallback N)" suffix instead of the bare id. */
const CHAIN_STEP_LABELS: Record<string, string> = { parse: "Parsing", embed: "Embedding" };
const CHAIN_STEP_ID = /^(parse|embed)_(\d+)$/;

/** snake_case → "Title Case" — the fallback for any id not curated above. */
function autoHumanize(id: string): string {
  return id.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

/** The readable label a job's stage/node id should render as — the raw id itself belongs in a
 *  tooltip/title next to it, never dropped. */
export function humanizeStageId(id: string): string {
  if (id in STAGE_LABELS) return STAGE_LABELS[id];
  const chainStep = CHAIN_STEP_ID.exec(id);
  if (chainStep) return `${CHAIN_STEP_LABELS[chainStep[1]]} (fallback ${Number(chainStep[2]) + 1})`;
  return autoHumanize(id);
}
