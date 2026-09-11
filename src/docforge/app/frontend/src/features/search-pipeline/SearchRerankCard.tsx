// ====== Code Summary ======
// The reranking step of the search rail — the one toggleable step (topology edit, see blobOps).
// Drawn like an ingestion stage: a StageSwitch in the control slot, greyed when off, so the whole
// canonical chain stays on screen whether or not reranking is enabled. Carries a fixed scroll
// anchor (there is only ever one instance of this card) so the minimap can jump-scroll to it —
// see state/searchMinimapEntries.ts's `RERANK_MINIMAP_KEY`, which must match this literal.
// While off, shows the same amber caveat the ingestion stage rail gives its own provider-hosted
// off-by-default stages ("Provider-hosted — ships off…", see ingest/stages/view.py's `__notes`) —
// this one is a static client-side string (no backend notes field on the search view today) that
// also calls out the local BGE cross-encoder's CPU cost, since a naive enable here is the one search
// stage that can tank latency badly on this deployment's hardware.

import { theme as t } from "../../theme";
import { StageSwitch } from "../stage-rail/StageSwitch";
import { SearchStageFrame } from "./SearchStageFrame";
import { RERANK_MINIMAP_KEY } from "./state/searchMinimapEntries";
import { StepNumberBadge } from "./StepNumberBadge";

const OFF_NOTE =
  "Provider-hosted — ships off. Enable it and point it at a reachable cross-encoder endpoint; " +
  "the default local CPU reranker is NOT recommended for production use (high per-query latency) " +
  "— prefer a GPU-hosted or provider-hosted endpoint.";

interface SearchRerankCardProps {
  /** This step's position in the rail — omitted only in the rare topology where `retrieve` itself
   *  is missing (see SearchPipelineRail's `!hasAnchor` fallback), so numbering stays consistent
   *  with every other step ("all numbered or none", never a lone unnumbered card mid-rail). */
  step?: number;
  enabled: boolean;
  onToggle: (next: boolean) => void;
}

export function SearchRerankCard({ step, enabled, onToggle }: SearchRerankCardProps) {
  const control = <StageSwitch checked={enabled} onChange={onToggle} title={enabled ? "Disable reranking" : "Enable reranking"} />;
  const left = step === undefined ? control : (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: t.space.xs }}>
      <StepNumberBadge step={step} />
      {control}
    </div>
  );
  return (
    <SearchStageFrame
      left={left}
      title="Reranking"
      tag="rerank"
      summary="Re-ranks the top results with a cross-encoder (BGE)."
      note={enabled ? undefined : OFF_NOTE}
      enabled={enabled}
      anchorKey={RERANK_MINIMAP_KEY}
    />
  );
}
