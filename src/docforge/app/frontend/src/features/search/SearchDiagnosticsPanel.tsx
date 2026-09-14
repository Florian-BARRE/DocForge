// ====== Code Summary ======
// Below-the-results "Diagnostics" disclosure — the run's `debug_info` (how the search actually ran:
// degraded axes, rewrite/HyDE notes, whatever the backend chose to report) plus the per-run paid-LLM
// cost line (query rewrite / HyDE spend), rendered mono like every other machine value in the app.
// Absent-field safe: an older response with neither field renders nothing (no dead disclosure).

import type { SearchCostModel } from "../../api/search";
import { theme } from "../../theme";
import { AdvancedDisclosure } from "../search-pipeline/AdvancedDisclosure";

interface SearchDiagnosticsPanelProps {
  debugInfo: Record<string, unknown> | null | undefined;
  cost: SearchCostModel | null | undefined;
}

/** Renders a debug_info value readably: primitives as-is, objects/arrays pretty-printed JSON. */
function formatDebugValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function DebugRow({ label, value }: { label: string; value: unknown }) {
  const formatted = formatDebugValue(value);
  const multiline = formatted.includes("\n");
  return (
    <div style={{ display: "flex", flexDirection: multiline ? "column" : "row", gap: theme.space.xs, justifyContent: "space-between" }}>
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{label}</span>
      <span
        style={{
          fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.text,
          whiteSpace: multiline ? "pre-wrap" : "nowrap", textAlign: multiline ? "left" : "right",
        }}
      >
        {formatted}
      </span>
    </div>
  );
}

function CostLine({ cost }: { cost: SearchCostModel }) {
  const costLabel = cost.cost_usd === null ? "—" : `$${cost.cost_usd.toFixed(4)}`;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m }}>
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>Query-time LLM spend</span>
      <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.text }}>
        {cost.prompt_tokens}+{cost.completion_tokens} tok · {costLabel} · {cost.call_count} call{cost.call_count === 1 ? "" : "s"}
      </span>
    </div>
  );
}

export function SearchDiagnosticsPanel({ debugInfo, cost }: SearchDiagnosticsPanelProps) {
  const debugEntries = debugInfo ? Object.entries(debugInfo) : [];
  if (debugEntries.length === 0 && !cost) return null;

  return (
    <AdvancedDisclosure summary="Diagnostics">
      {cost && <CostLine cost={cost} />}
      {debugEntries.map(([key, value]) => (
        <DebugRow key={key} label={key} value={value} />
      ))}
    </AdvancedDisclosure>
  );
}
