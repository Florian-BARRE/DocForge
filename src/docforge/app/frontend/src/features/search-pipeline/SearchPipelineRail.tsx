// ====== Code Summary ======
// The connected rail of search-pipeline steps — one numbered card per blob node, in blob order,
// plus Reranking (the one other toggleable, numbered top-level step) spliced in right after its
// canonical anchor node (`retrieve`) so the whole chain reads top-to-bottom exactly like the
// backend topology. Query understanding is NOT a sibling step: it's nested inside `normalize`'s own
// card (SearchNodeCard's `extra` slot) since it's a modifier of step 1, not a step of its own —
// keeps numbering either "every top-level card" or "none", never a mix. Pure render: every gesture
// is handed straight to the caller-owned edit functions.

import { Fragment } from "react";
import type { ActionBlob, GroupBlob, Palette } from "../../api/types";
import { StageConnector } from "../stage-rail/StageConnector";
import { SearchNodeCard } from "./SearchNodeCard";
import { SearchQueryCard } from "./SearchQueryCard";
import { SearchRerankCard } from "./SearchRerankCard";
import { isRerankEnabled, type QueryTransformKind } from "./state/blobOps";
// Same anchor ids `useSearchPipelineEditor` used to compute `hasAnchor`/`hasQueryAnchor`.
import { QUERY_ANCHOR_ID, RERANK_ANCHOR_ID } from "./state/useSearchPipelineEditor";

interface SearchPipelineRailProps {
  blob: GroupBlob;
  palette: Palette;
  railNodes: ActionBlob[];
  hasAnchor: boolean;
  hasQueryAnchor: boolean;
  queryKind: QueryTransformKind | null;
  queryConfig: { config: Record<string, unknown> } | undefined;
  onChangeNodeConfig: (nodeId: string, field: string, value: unknown) => void;
  onSelectQueryTransform: (kind: QueryTransformKind | null) => void;
  onToggleRerank: (next: boolean) => void;
}

export function SearchPipelineRail({
  blob, palette, railNodes, hasAnchor, hasQueryAnchor, queryKind, queryConfig,
  onChangeNodeConfig, onSelectQueryTransform, onToggleRerank,
}: SearchPipelineRailProps) {
  const queryExtra = (
    <SearchQueryCard
      nested
      active={queryKind}
      config={queryConfig?.config ?? null}
      onSelect={onSelectQueryTransform}
      onChangeConfig={(field, value) => {
        if (queryKind) onChangeNodeConfig(queryKind, field, value);
      }}
    />
  );

  // Reranking occupies a real numbered slot right after `retrieve` — count it into the same
  // sequence as the plain nodes rather than assigning numbers purely from `railNodes`' own index,
  // so every card downstream of the splice still reads its correct position.
  const rerankIndexInRail = railNodes.findIndex((node) => node.id === RERANK_ANCHOR_ID);
  const stepFor = (nodeIndex: number) => (hasAnchor && nodeIndex > rerankIndexInRail ? nodeIndex + 2 : nodeIndex + 1);
  const rerankStep = hasAnchor ? rerankIndexInRail + 2 : railNodes.length + 1;

  return (
    // One connected rail — the same pattern as the ingestion stage rail. Reranking is the one
    // toggleable step; it's rendered right after `retrieve`, staying visible (greyed) when off
    // so the whole canonical chain is always on screen.
    <div className="df-stagger" style={{ display: "flex", flexDirection: "column" }}>
      {railNodes.map((node, index) => (
        <Fragment key={node.id}>
          {index > 0 && <StageConnector />}
          <SearchNodeCard
            step={stepFor(index)}
            node={node}
            palette={palette}
            onChangeConfig={(field, value) => onChangeNodeConfig(node.id, field, value)}
            extra={node.id === QUERY_ANCHOR_ID ? queryExtra : undefined}
          />
          {node.id === RERANK_ANCHOR_ID && (
            <>
              <StageConnector />
              <SearchRerankCard step={rerankStep} enabled={isRerankEnabled(blob)} onToggle={onToggleRerank} />
            </>
          )}
        </Fragment>
      ))}
      {!hasQueryAnchor && (
        <>
          {railNodes.length > 0 && <StageConnector />}
          {/* Fallback for the rare custom blob without a `normalize` node to nest under — falls
              back to its own (unnumbered) card since there's no step 1 to fold into. */}
          <SearchQueryCard
            active={queryKind}
            config={queryConfig?.config ?? null}
            onSelect={onSelectQueryTransform}
            onChangeConfig={(field, value) => {
              if (queryKind) onChangeNodeConfig(queryKind, field, value);
            }}
          />
        </>
      )}
      {!hasAnchor && (
        <>
          {(railNodes.length > 0 || !hasQueryAnchor) && <StageConnector />}
          <SearchRerankCard step={rerankStep} enabled={isRerankEnabled(blob)} onToggle={onToggleRerank} />
        </>
      )}
    </div>
  );
}
