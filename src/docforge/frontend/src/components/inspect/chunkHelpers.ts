// ====== Code Summary ======
// Pure helpers shared across the ChunkBrowser sub-components: page extraction
// from chunk provenance, heading-path lookup, embed/raw header split, and the
// block-type colour map.

// ====== Internal Project Imports ======
import type { ChunkResponse } from '../../api/types'

/**
 * Extract the page indices a chunk spans from its provenance dictionary.
 *
 * Args:
 *   c: Chunk record.
 *
 * Returns:
 *   The list of page indices, or an empty array when absent.
 */
export function chunkPages(c: ChunkResponse): number[] {
  const prov = c.prov as Record<string, unknown> | undefined
  const pages = prov?.pages
  return Array.isArray(pages) ? (pages as number[]) : []
}

/**
 * Return the first page index of a chunk, or Infinity when it has none.
 *
 * Args:
 *   c: Chunk record.
 *
 * Returns:
 *   The first page index, or Infinity (used for stable sorting).
 */
export function firstPage(c: ChunkResponse): number {
  const p = chunkPages(c)
  return p.length > 0 ? p[0] : Infinity
}

/**
 * Read the breadcrumb heading path a chunk carries in its provenance.
 *
 * Args:
 *   c: Chunk record.
 *
 * Returns:
 *   The heading-path string, or null when absent.
 */
export function chunkHeadingPath(c: ChunkResponse): string | null {
  const prov = c.prov as Record<string, unknown> | undefined
  const hp = prov?.heading_path
  return typeof hp === 'string' ? hp : null
}

/**
 * Split a chunk's embed_text into the S5-prepended header and the chunk body.
 *
 * Args:
 *   c: Chunk record.
 *
 * Returns:
 *   An object with headerPart (S5 breadcrumb prefix) and bodyPart (raw body).
 */
export function splitEmbedHeader(c: ChunkResponse): { headerPart: string; bodyPart: string } {
  const idx = c.embed_text.lastIndexOf(c.raw_text)
  if (idx <= 0) return { headerPart: '', bodyPart: c.embed_text }
  return {
    headerPart: c.embed_text.slice(0, idx),
    bodyPart: c.embed_text.slice(idx),
  }
}

/**
 * Map an IR block type to its display colour.
 *
 * Args:
 *   type: Block type string (case-insensitive).
 *
 * Returns:
 *   A hex colour string for the block type.
 */
export function blockTypeColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'heading':       return '#a78bfa'
    case 'paragraph':     return '#94a3b8'
    case 'figure':        return '#6366f1'
    case 'table':         return '#34d399'
    case 'list_item':     return '#60a5fa'
    case 'caption':       return '#f59e0b'
    case 'code':          return '#f97316'
    case 'formula':       return '#ec4899'
    case 'header_footer': return '#64748b'
    default:              return '#94a3b8'
  }
}
