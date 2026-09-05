// ====== Code Summary ======
// Pure helpers that reconstruct HOW a chunk was assembled, for the Layout view's chunk + provenance
// columns: which span of the embedded text each source IR block contributed (so the chunk text can be
// coloured by the SAME per-type colours as the blocks), and what the pipeline ADDED on top (section
// breadcrumb, folded figure OCR/VLM text, generated metadata) with the stage/method that produced it.

import type { ChunkInfo, IRBlock, IREnrichment, IRTable } from "../../../api/explorer";
import { humanizeEnumOption } from "../../../components/schema-form/fieldLabels";

/** A block plus its reading-order number in the row (1-based shown, 0-based stored index). */
export interface ChunkMember {
  block: IRBlock;
  index: number;
}

// Raw block_type strings (lower-cased) the backend's PassageProjector treats as a heading / a table —
// mirrors BlockType.HEADING / BlockType.TABLE plus the docling synonyms blockColors.ts already maps.
const HEADING_BLOCK_TYPES = new Set(["heading", "title", "section_header"]);
const TABLE_BLOCK_TYPES = new Set(["table"]);

function isHeadingBlock(block: IRBlock): boolean {
  return HEADING_BLOCK_TYPES.has(block.block_type.toLowerCase());
}

function isTableBlock(block: IRBlock): boolean {
  return TABLE_BLOCK_TYPES.has(block.block_type.toLowerCase());
}

/** Conservative comparison key — lowercased, trimmed, whitespace-collapsed — mirrors the backend's
 *  `ChunkerHelpers.normalize_text` used to detect a heading duplicating its own section's first line. */
function normalizeForCompare(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

/** Escape a table cell the same way the backend's markdown grid does (pipes escaped, breaks flattened). */
function sanitizeTableCell(cell: unknown): string {
  const raw = cell == null ? "" : String(cell);
  return raw.replace(/\\/g, "\\\\").replace(/\|/g, "\\|").replace(/[\n\r]/g, " ");
}

/**
 * Render an IR table as the SAME markdown grid the chunker embeds into a chunk's text — mirrors
 * `ChunkerHelpers.render_table` / its `__markdown_grid` (shared/libs/pipelines/ingest/nodes/chunk/base/
 * helpers.py) byte-for-byte, since this is the exact needle `segmentChunkText` must find.
 */
export function renderTableMarkdown(table: IRTable): string | null {
  const rows: unknown[][] = Array.isArray(table.cells) ? (table.cells as unknown[][]) : [];
  const nCols = rows.reduce((max, row) => Math.max(max, Array.isArray(row) ? row.length : 0), 0);
  if (nCols === 0) return null;
  const lines = rows.map((row) => {
    const cells = (Array.isArray(row) ? row : []).map(sanitizeTableCell);
    while (cells.length < nCols) cells.push("");
    return `| ${cells.join(" | ")} |`;
  });
  if (table.has_header) lines.splice(1, 0, `|${" --- |".repeat(nCols)}`);
  return lines.join("\n");
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

/**
 * The text a block contributes to a chunk — a table's rendered markdown grid, its native text, or a
 * figure's folded OCR/VLM text. Mirrors `PassageProjector.__block_text`'s per-type dispatch so the
 * needle matches exactly what the chunker actually embedded.
 */
function contributedText(block: IRBlock, enrichments: IREnrichment[], table: IRTable | undefined): string | null {
  if (isTableBlock(block) && table) {
    const rendered = renderTableMarkdown(table);
    if (rendered) return rendered;
  }
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
 *
 * A CARRIED heading needs one extra rule: `BaseChunkerNode.__prepend_heading` drops a heading's title
 * entirely (contributes NO text of its own) when it duplicates the very next passage's first line — the
 * heading's block id still travels in `block_ids` for provenance, but a naive lookup would otherwise let
 * its needle match the next block's OWN leading words, stealing them from that block's segment. Such a
 * heading is skipped here exactly like the chunker skipped its text, so the next block still owns it.
 */
export function segmentChunkText(
  chunkText: string,
  members: ChunkMember[],
  enrichmentsByBlock: Map<string, IREnrichment[]>,
  tablesByBlock: Map<string, IRTable> = new Map(),
): ChunkSegment[] {
  const segments: ChunkSegment[] = [];
  let cursor = 0;
  for (let i = 0; i < members.length; i += 1) {
    const { block, index } = members[i];
    const needle = contributedText(block, enrichmentsByBlock.get(block.id) ?? [], tablesByBlock.get(block.id));
    if (!needle) continue;
    if (isHeadingBlock(block) && duplicatesNextMember(needle, members[i + 1], enrichmentsByBlock, tablesByBlock)) continue;
    const at = chunkText.indexOf(needle, cursor);
    if (at < 0) continue;
    if (at > cursor) segments.push({ text: chunkText.slice(cursor, at), added: true });
    segments.push({ text: chunkText.slice(at, at + needle.length), blockType: block.block_type, blockIndex: index, added: false });
    cursor = at + needle.length;
  }
  if (cursor < chunkText.length) segments.push({ text: chunkText.slice(cursor), added: true });
  return segments;
}

/** True when a heading's own needle is (conservatively) identical to the next member's first line. */
function duplicatesNextMember(
  headingNeedle: string,
  next: ChunkMember | undefined,
  enrichmentsByBlock: Map<string, IREnrichment[]>,
  tablesByBlock: Map<string, IRTable>,
): boolean {
  if (!next) return false;
  const nextNeedle = contributedText(next.block, enrichmentsByBlock.get(next.block.id) ?? [], tablesByBlock.get(next.block.id));
  if (!nextNeedle) return false;
  const firstLine = nextNeedle.split("\n", 1)[0];
  return normalizeForCompare(headingNeedle) === normalizeForCompare(firstLine);
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
