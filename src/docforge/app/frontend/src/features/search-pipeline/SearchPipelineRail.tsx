// ====== Code Summary ======
// The connected rail of search-pipeline steps — one card per blob node, in blob order, plus the
// two toggleable cards (query transform, rerank) spliced in right after their canonical anchor
// node (`normalize` / `retrieve`) so the whole chain reads top-to-bottom exactly like the backend
// topology. Pure render: every gesture is handed straight to the caller-owned edit functions.

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
  const queryCard = (
    <SearchQueryCard
      active={queryKind}
      config={queryConfig?.config ?? null}
      onSelect={onSelectQueryTransform}
      onChangeConfig={(field, value) => {
        if (queryKind) onChangeNodeConfig(queryKind, field, value);
      }}
    />
  );

  return (
    // One connected rail — the same pattern as the ingestion stage rail. Reranking is the one
    // toggleable step; it's rendered right after `retrieve`, staying visible (greyed) when off
    // so the whole canonical chain is always on screen.
    <div className="df-stagger" style={{ display: "flex", flexDirection: "column" }}>
      {railNodes.map((node, index) => (
        <Fragment key={node.id}>
          {index > 0 && <StageConnector />}
          <SearchNodeCard
            step={index + 1}
            node={node}
            palette={palette}
            onChangeConfig={(field, value) => onChangeNodeConfig(node.id, field, value)}
          />
          {node.id === QUERY_ANCHOR_ID && (
            <>
              <StageConnector />
              {queryCard}
            </>
          )}
          {node.id === RERANK_ANCHOR_ID && (
            <>
              <StageConnector />
              <SearchRerankCard enabled={isRerankEnabled(blob)} onToggle={onToggleRerank} />
            </>
          )}
        </Fragment>
      ))}
      {!hasQueryAnchor && (
        <>
          {railNodes.length > 0 && <StageConnector />}
          {queryCard}
        </>
      )}
      {!hasAnchor && (
        <>
          {(railNodes.length > 0 || !hasQueryAnchor) && <StageConnector />}
          <SearchRerankCard enabled={isRerankEnabled(blob)} onToggle={onToggleRerank} />
        </>
      )}
    </div>
  );
}
