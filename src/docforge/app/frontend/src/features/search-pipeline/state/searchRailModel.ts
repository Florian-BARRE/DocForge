// ====== Code Summary ======
// Pure derivations of the search pipeline editor's rail (useSearchPipelineEditor): the anchor ids
// the toggleable cards are spliced after, which blob nodes the rail draws, and the query-transform
// node's config. No React — the hook memoises these on the blob.

import type { ActionBlob, GroupBlob } from "../../../api/types";
import { isActionBlob, queryTransformKind, type QueryTransformKind } from "./blobOps";

// The read-only step the toggleable reranking card is rendered right after (matches the backend's
// retrieve → rerank → hydrate splice in blobOps). `SearchPipelineRail` splices its card at the same
// anchor.
export const RERANK_ANCHOR_ID = "retrieve";
// The query-transform card is rendered right after `normalize` — the point its rewrite/HyDE node is
// spliced in (normalize → transform → encode, see blobOps.setQueryTransform). Exported for the same
// reason as `RERANK_ANCHOR_ID`.
export const QUERY_ANCHOR_ID = "normalize";

/**
 * The rail's read-only/config steps — rerank AND the query transform are drawn as their own
 * toggleable cards, so both are filtered out here to avoid rendering them twice. `normalize` stays
 * (it shares the `query` family but is the fixed first step, not a transform).
 */
export function railNodesOf(blob: GroupBlob | null): ActionBlob[] {
  return blob
    ? blob.nodes
        .filter(isActionBlob)
        .filter((node) => node.family !== "rerank")
        .filter((node) => !(node.family === "query" && node.kind !== "normalize"))
    : [];
}

/** Whether a node with this id is among the rail nodes. */
export function hasRailNode(railNodes: { id: string }[], id: string): boolean {
  return railNodes.some((node) => node.id === id);
}

/** The active query transform (rewrite / HyDE / none) of the blob. */
export function queryKindOf(blob: GroupBlob | null): QueryTransformKind | null {
  return blob ? queryTransformKind(blob) : null;
}

/** The config of the active query-transform node (the node id equals the transform kind). */
export function queryConfigOf(
  blob: GroupBlob | null,
  queryKind: QueryTransformKind | null,
): { config: Record<string, unknown> } | undefined {
  return blob?.nodes.find((node) => isActionBlob(node) && node.id === queryKind) as
    | { config: Record<string, unknown> }
    | undefined;
}
