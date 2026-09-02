// ====== Code Summary ======
// One pipeline stage's row in the breakdown table — stage/family, provider/model, calls (plus a
// page-count hint for per-page-billed stages like OCR/parse), prompt→completion tokens, and the
// projected cost. Every machine value is JetBrains Mono per brand.md; an unpriced stage (no
// configured provider rate) shows a quiet "unpriced" chip instead of a dash.

import type { CostEstimateStage } from "../../../api/collections";
import { Chip } from "../../../components/Chip";
import { theme as t } from "../../../theme";
import { formatUsd } from "./estimateFormat";

interface CostEstimateStageRowProps {
  stage: CostEstimateStage;
}

const cellStyle: React.CSSProperties = { padding: `${t.space.s}px ${t.space.m}px`, fontSize: t.font.size.s, verticalAlign: "top" };
const numCellStyle: React.CSSProperties = { ...cellStyle, textAlign: "right" };
const subStyle: React.CSSProperties = { fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute, marginTop: 2 };

export function CostEstimateStageRow({ stage }: CostEstimateStageRowProps) {
  const totalTokens = stage.prompt_tokens + stage.completion_tokens;

  return (
    <tr style={{ borderBottom: `1px solid ${t.color.line}` }}>
      <td style={cellStyle}>
        <div style={{ fontWeight: t.font.weight.medium, color: t.color.text }}>{stage.stage}</div>
        <div style={subStyle}>{stage.family}</div>
      </td>
      <td style={cellStyle}>
        <div style={{ color: t.color.text }}>{stage.provider}</div>
        {stage.model && <div style={subStyle}>{stage.model}</div>}
      </td>
      <td style={numCellStyle}>
        <span style={{ fontFamily: t.font.mono, color: t.color.text }}>{stage.calls.toLocaleString()}</span>
        {stage.pages > 0 && <div style={subStyle}>{stage.pages.toLocaleString()} pages</div>}
      </td>
      <td style={numCellStyle}>
        <span style={{ fontFamily: t.font.mono, color: t.color.text }}>{totalTokens.toLocaleString()}</span>
        {totalTokens > 0 && (
          <div style={subStyle}>{stage.prompt_tokens.toLocaleString()} in · {stage.completion_tokens.toLocaleString()} out</div>
        )}
      </td>
      <td style={numCellStyle}>
        {stage.rate_known && stage.cost_usd !== null ? (
          <span style={{ fontFamily: t.font.mono, color: t.color.text, fontWeight: t.font.weight.semibold }}>{formatUsd(stage.cost_usd)}</span>
        ) : (
          <Chip tone="dim" title="This provider has no configured rate — its cost is excluded from the total.">unpriced</Chip>
        )}
      </td>
    </tr>
  );
}
