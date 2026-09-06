// ====== Code Summary ======
// The search-pipeline minimap's flat step list — one entry per rail node PLUS the always-visible
// Reranking step (greyed when off, never hidden, per the fixed-shape mandate), spliced in at the
// SAME position `SearchPipelineRail` renders its card, so the count of circles always matches the
// count of cards on screen (6 steps in the canonical topology: normalize, encode, retrieve,
// reranking, hydrate, deliver).

import { findNodeCard } from "../../../components/schema-form/paletteLookup";
import type { ActionBlob, GroupBlob, Palette } from "../../../api/types";
import { isRerankEnabled } from "./blobOps";
import { RERANK_ANCHOR_ID } from "./useSearchPipelineEditor";

/** One minimap circle: a stable key (matches the card's `anchorKey`), its label, and whether the
 *  step is currently active (greys out an off-but-always-visible step, e.g. reranking). */
export interface SearchMinimapEntry {
  key: string;
  title: string;
  enabled: boolean;
}

/** The Reranking step's fixed anchor/minimap key — there is only ever one instance of this card. */
export const RERANK_MINIMAP_KEY = "rerank";

/**
 * Derives the minimap's step list from the same data `SearchPipelineRail` renders from.
 *
 * Args:
 *   blob: The current search graph blob (source of the rerank on/off state).
 *   palette: The search pipeline's palette (node titles).
 *   railNodes: The ordered rail nodes, same list `SearchPipelineRail` iterates.
 *   hasAnchor: Whether `retrieve` (the rerank splice point) is present in `railNodes`.
 *
 * Returns:
 *   list[SearchMinimapEntry]: One entry per card, in on-screen order.
 */
export function deriveSearchMinimapEntries(
  blob: GroupBlob,
  palette: Palette,
  railNodes: ActionBlob[],
  hasAnchor: boolean,
): SearchMinimapEntry[] {
  const rerankEntry: SearchMinimapEntry = {
    key: RERANK_MINIMAP_KEY,
    title: "Reranking",
    enabled: isRerankEnabled(blob),
  };

  const entries: SearchMinimapEntry[] = [];
  for (const node of railNodes) {
    const card = findNodeCard(palette, node.family, node.kind);
    entries.push({ key: node.id, title: card?.name ?? node.kind, enabled: true });
    if (node.id === RERANK_ANCHOR_ID) entries.push(rerankEntry);
  }
  // The rare topology where `retrieve` itself is missing — SearchPipelineRail falls back to
  // rendering the rerank card at the very end (see its own `!hasAnchor` branch); mirror that here.
  if (!hasAnchor) entries.push(rerankEntry);
  return entries;
}
