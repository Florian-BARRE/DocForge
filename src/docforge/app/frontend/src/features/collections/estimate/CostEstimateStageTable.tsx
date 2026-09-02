// ====== Code Summary ======
// The per-stage cost/volume breakdown table — one row per priced pipeline step, server order
// preserved (no client sort; the list is short and already stage-ordered). Renders nothing when
// the pipeline has no priceable stage at all (a pure parse-only pipeline still reports volume via
// CostEstimateHeadline, so an empty table here is not an error state).

import type { CostEstimateStage } from "../../../api/collections";
import { theme as t } from "../../../theme";
import { CostEstimateStageRow } from "./CostEstimateStageRow";

interface CostEstimateStageTableProps {
  stages: CostEstimateStage[];
}

const COLUMNS = ["Stage", "Provider / model", "Calls", "Tokens", "Cost"];

export function CostEstimateStageTable({ stages }: CostEstimateStageTableProps) {
  if (stages.length === 0)
    return (
      <div style={{ border: `1px dashed ${t.color.lineStrong}`, borderRadius: t.radius.l, padding: t.space.xl, textAlign: "center", color: t.color.dim, fontSize: t.font.size.m }}>
        No priceable stage in this pipeline — parsing/chunking alone has no per-call provider cost.
      </div>
    );

  return (
    <div>
      <div style={{ fontFamily: t.font.display, fontWeight: t.font.weight.semibold, fontSize: t.font.size.l, color: t.color.text, marginBottom: t.space.s }}>
        Per-stage breakdown
      </div>
      <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, overflow: "hidden" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${t.color.line}` }}>
              {COLUMNS.map((label, index) => (
                <th
                  key={label}
                  style={{
                    textAlign: index === 0 || index === 1 ? "left" : "right", color: t.color.dim, fontSize: t.font.size.xs,
                    padding: `${t.space.s}px ${t.space.m}px`, fontWeight: t.font.weight.semibold,
                    textTransform: "uppercase", letterSpacing: "0.04em",
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stages.map((stage, index) => (
              <CostEstimateStageRow key={`${stage.stage}-${index}`} stage={stage} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
