// ====== Code Summary ======
// The reranking step of the search rail — the one toggleable step (topology edit, see blobOps).
// Drawn like an ingestion stage: a StageSwitch in the control slot, greyed when off, so the whole
// canonical chain stays on screen whether or not reranking is enabled.

import { StageSwitch } from "../stage-rail/StageSwitch";
import { SearchStageFrame } from "./SearchStageFrame";

interface SearchRerankCardProps {
  enabled: boolean;
  onToggle: (next: boolean) => void;
}

export function SearchRerankCard({ enabled, onToggle }: SearchRerankCardProps) {
  return (
    <SearchStageFrame
      left={<StageSwitch checked={enabled} onChange={onToggle} title={enabled ? "Disable reranking" : "Enable reranking"} />}
      title="Reranking"
      tag="rerank"
      summary="Re-ranks the top results with a cross-encoder (BGE)."
      enabled={enabled}
    />
  );
}
