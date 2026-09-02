// ====== Code Summary ======
// The estimate result's headline — the projected total spend (or "Free"/"Cost unknown" when
// unpriced, per the endpoint's null-vs-zero distinction), a "partial" flag when some stages
// couldn't be priced, and a mini-grid of the projected output volume. Mirrors
// storage/StorageGrandTotal's big-mono-headline shape.

import type { CostEstimate } from "../../../api/collections";
import { Chip } from "../../../components/Chip";
import { theme as t } from "../../../theme";
import { CostEstimateVolumeStat } from "./CostEstimateVolumeStat";
import { formatBytes, formatUsd } from "./estimateFormat";

interface CostEstimateHeadlineProps {
  estimate: CostEstimate;
}

function costHeadline(totalCostUsd: number | null): string {
  if (totalCostUsd === null) return "Cost unknown";
  if (totalCostUsd === 0) return "Free";
  return formatUsd(totalCostUsd);
}

export function CostEstimateHeadline({ estimate }: CostEstimateHeadlineProps) {
  const { document_count, volume, total_prompt_tokens, total_completion_tokens, total_cost_usd, cost_complete } = estimate;
  const totalTokens = total_prompt_tokens + total_completion_tokens;

  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: t.space.l }}>
      <div>
        <div style={{ color: t.color.mute, fontSize: t.font.size.xs, fontWeight: t.font.weight.bold, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Estimated cost
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: t.space.s, marginTop: 4 }}>
          <span style={{ fontFamily: t.font.mono, fontWeight: t.font.weight.bold, fontSize: t.font.size.display, color: t.color.text, lineHeight: 1.1 }}>
            {costHeadline(total_cost_usd)}
          </span>
          {!cost_complete && (
            <Chip tone="warn" title="At least one priced stage's provider has no configured rate — the total understates the real spend.">
              partial
            </Chip>
          )}
        </div>
        <div style={{ color: t.color.mute, fontSize: t.font.size.s, marginTop: 4 }}>
          across {document_count} document{document_count === 1 ? "" : "s"} ·{" "}
          <span style={{ fontFamily: t.font.mono }}>{totalTokens.toLocaleString()}</span> tokens
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))", gap: t.space.m, flex: "1 1 320px", minWidth: 260 }}>
        <CostEstimateVolumeStat label="Pages" value={volume.pages.toLocaleString()} />
        <CostEstimateVolumeStat label="Chunks" value={volume.chunks.toLocaleString()} />
        <CostEstimateVolumeStat label="Dense vectors" value={volume.dense_vectors.toLocaleString()} />
        <CostEstimateVolumeStat label="Sparse vectors" value={volume.sparse_vectors.toLocaleString()} />
        <CostEstimateVolumeStat label="Storage" value={formatBytes(volume.storage_bytes)} />
      </div>
    </div>
  );
}
