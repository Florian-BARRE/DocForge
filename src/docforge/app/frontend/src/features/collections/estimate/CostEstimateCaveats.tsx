// ====== Code Summary ======
// The estimate's fine print — a fixed "this is a projection, not a bill" note plus the backend's
// own scope/provider-specific caveats[], and a collapsed disclosure of the raw assumptions[] the
// numbers rest on (rate figures, sampled ratios). Quiet/neutral styling — this is context, not a
// warning; the actual "some stages unpriced" caution lives on the headline's chip instead.

import type { CostEstimate } from "../../../api/collections";
import { theme as t } from "../../../theme";
import { AdvancedDisclosure } from "../../search-pipeline/AdvancedDisclosure";
import { humanizeAssumptionKey } from "./estimateFormat";

interface CostEstimateCaveatsProps {
  estimate: CostEstimate;
}

export function CostEstimateCaveats({ estimate }: CostEstimateCaveatsProps) {
  const assumptionEntries = Object.entries(estimate.assumptions);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.m }}>
      <div
        style={{
          background: t.color.surface2, border: `1px solid ${t.color.line}`, borderRadius: t.radius.m,
          padding: t.space.m, fontSize: t.font.size.s, color: t.color.dim,
        }}
      >
        <div style={{ color: t.color.text, fontWeight: t.font.weight.medium, marginBottom: estimate.caveats.length ? t.space.xs : 0 }}>
          These are estimates, not a bill — projected from current provider rates and sampled statistics; actual usage may differ.
        </div>
        {estimate.caveats.length > 0 && (
          <ul style={{ margin: 0, paddingLeft: t.space.l }}>
            {estimate.caveats.map((caveat, index) => (
              <li key={index}>{caveat}</li>
            ))}
          </ul>
        )}
      </div>

      {assumptionEntries.length > 0 && (
        <AdvancedDisclosure summary="Assumptions">
          {assumptionEntries.map(([key, value]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: t.space.m, padding: `${t.space.xs}px 0` }}>
              <span style={{ color: t.color.dim, fontSize: t.font.size.s }}>{humanizeAssumptionKey(key)}</span>
              <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.s, color: t.color.text }}>{String(value)}</span>
            </div>
          ))}
        </AdvancedDisclosure>
      )}
    </div>
  );
}
