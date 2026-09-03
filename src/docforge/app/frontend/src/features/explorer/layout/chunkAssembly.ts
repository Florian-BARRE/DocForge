// ====== Code Summary ======
// Pure helpers that reconstruct HOW a chunk was assembled, for the Layout view's chunk + provenance
// columns: which span of the embedded text each source IR block contributed (so the chunk text can be
// coloured by the SAME per-type colours as the blocks), and what the pipeline ADDED on top (section
// breadcrumb, folded figure OCR/VLM text, generated metadata) with the stage/method that produced it.

import type { ChunkInfo, IRBlock, IREnrichment } from "../../../api/explorer";
import { humanizeEnumOption } from "../../../components/schema-form/fieldLabels";

/** A block plus its reading-order number in the row (1-based shown, 0-based stored index). */
export interface ChunkMember {
  block: IRBlock;
  index: number;
}

/** One run of a chunk's embedded text: either a source block's contribution or pipeline-added glue. */
export interface ChunkSegment {
  text: string;
  /** Source block's raw type (drives its colour); absent on added glue. */
  blockType?: string;
  /** Source block's reading-order number (0-based); absent on added glue. */
  blockIndex?: number;
  added: boolean;
}

/** One thing the pipeline ADDED to a chunk, with where it came from (increasing precision rightward). */
export interface ProvenanceItem {
  id: string;
  kind: "breadcrumb" | "enrichment" | "metadata";
  label: string;
  detail: string;
  stage: string;
  method: string;
}

/** The text a block contributes to a chunk — its native text, or a figure's folded OCR/VLM text. */
function contributedText(block: IRBlock, enrichments: IREnrichment[]): string | null {
  if (block.text && block.text.trim()) return block.text.trim();
  const ocr = enrichments.find((e) => e.kind === "ocr" && e.status === "ok" && e.text);
  if (ocr?.text) return ocr.text.trim();
  const vlm = enrichments.find((e) => e.kind === "vlm" && e.status === "ok" && e.text);
  if (vlm?.text) return vlm.text.trim();
  return null;
}

/**
 * Split a chunk's embedded text into its source-block contributions + the pipeline-added glue between.
 *
 * Each member block's contributed text is located in reading order from a running cursor; the spans
 * that match become block segments (coloured by the block's type), and everything between/around them
 * (the breadcrumb, the contextual prefix) becomes `added` glue. Blocks whose text was reflowed and no
 * longer appears verbatim are skipped (their span just folds into surrounding glue) — never throws.
 */
export function segmentChunkText(
  chunkText: string,
  members: ChunkMember[],
  enrichmentsByBlock: Map<string, IREnrichment[]>,
): ChunkSegment[] {
  const segments: ChunkSegment[] = [];
  let cursor = 0;
  for (const { block, index } of members) {
    const needle = contributedText(block, enrichmentsByBlock.get(block.id) ?? []);
    if (!needle) continue;
    const at = chunkText.indexOf(needle, cursor);
    if (at < 0) continue;
    if (at > cursor) segments.push({ text: chunkText.slice(cursor, at), added: true });
    segments.push({ text: chunkText.slice(at, at + needle.length), blockType: block.block_type, blockIndex: index, added: false });
    cursor = at + needle.length;
  }
  if (cursor < chunkText.length) segments.push({ text: chunkText.slice(cursor), added: true });
  return segments;
}

/**
 * The pipeline-added parts of a chunk, each tagged with the stage + method that produced it.
 *
 * Breadcrumb → the contextualize stage; folded figure OCR/VLM → the enrich stage; each generated
 * metadata field → the metagen stage. This is the content of the rightmost "provenance" column.
 */
export function chunkProvenance(
  chunk: ChunkInfo,
  members: ChunkMember[],
  enrichmentsByBlock: Map<string, IREnrichment[]>,
): ProvenanceItem[] {
  const items: ProvenanceItem[] = [];

  // 1. Section breadcrumb prepended for retrieval context.
  if (chunk.heading_path.length > 0) {
    items.push({
      id: `${chunk.id}-breadcrumb`,
      kind: "breadcrumb",
      label: chunk.heading_path.join(" › "),
      detail: "Section breadcrumb prepended to the embedded text",
      stage: "contextualize",
      method: "breadcrumb",
    });
  }

  // 2. Figure OCR/VLM text folded into the chunk from its figure blocks.
  for (const { block, index } of members) {
    for (const enrichment of enrichmentsByBlock.get(block.id) ?? []) {
      if ((enrichment.kind === "ocr" || enrichment.kind === "vlm") && enrichment.status === "ok" && enrichment.text) {
        items.push({
          id: `${chunk.id}-${enrichment.id}`,
          kind: "enrichment",
          label: `${humanizeEnumOption(enrichment.kind)} · block ${index + 1}`,
          detail: "Figure text folded into the chunk",
          stage: "enrich",
          method: enrichment.kind,
        });
      }
    }
  }

  // 3. Generated metadata (the metagen stage).
  for (const meta of chunk.metadata) {
    if (meta.origin === "generated") {
      items.push({
        id: `${chunk.id}-meta-${meta.field_name}`,
        kind: "metadata",
        label: meta.field_name,
        detail: Array.isArray(meta.value) ? `${meta.value.length} value(s)` : String(meta.value),
        stage: "metagen",
        method: "llm",
      });
    }
  }

  return items;
}
