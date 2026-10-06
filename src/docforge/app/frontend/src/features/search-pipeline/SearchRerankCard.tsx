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
// stage that can tank latency badly on this deployment's hardware. While on, the node's own config
// form (base_url, api_key, top_n…, straight from the palette's config_schema) renders in the body.

import type { ActionBlob, Palette, ValidationIssue } from "../../api/types";
import { findNodeCard, hasConfigFields } from "../../components/schema-form/paletteLookup";
import { theme as t } from "../../theme";
import { StageSwitch } from "../stage-rail/StageSwitch";
import { NodeConfigForm } from "./NodeConfigForm";
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
  /** The blob's rerank node — absent only while the topology has none (i.e. while off). */
  node?: ActionBlob;
  palette?: Palette;
  onChangeConfig?: (field: string, value: unknown) => void;
  /** Current `/inspect` issues for the whole search blob — see `SchemaForm`'s own `issues` doc. */
  issues?: ValidationIssue[];
}

export function SearchRerankCard({ step, enabled, onToggle, node, palette, onChangeConfig, issues }: SearchRerankCardProps) {
  const form =
    enabled && node && palette && onChangeConfig && hasConfigFields(findNodeCard(palette, node.family, node.kind)) ? (
      <NodeConfigForm node={node} palette={palette} onChange={onChangeConfig} issues={issues} />
    ) : null;
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
    >
      {form}
    </SearchStageFrame>
  );
}
