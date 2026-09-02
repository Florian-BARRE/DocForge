// ====== Code Summary ======
// The reranking step of the search rail — the one toggleable step (topology edit, see blobOps).
// Drawn like an ingestion stage: a StageSwitch in the control slot, greyed when off, so the whole
// canonical chain stays on screen whether or not reranking is enabled.

import { theme as t } from "../../theme";
import { StageSwitch } from "../stage-rail/StageSwitch";
import { SearchStageFrame } from "./SearchStageFrame";
import { StepNumberBadge } from "./StepNumberBadge";

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
      enabled={enabled}
    />
  );
}
