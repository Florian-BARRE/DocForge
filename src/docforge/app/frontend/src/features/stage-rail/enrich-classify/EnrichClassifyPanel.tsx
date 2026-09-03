// ====== Code Summary ======
// The bespoke config surface for the enrich stage's figure-classify node — replacing the flat SchemaForm
// dump with a graph-native panel read top→bottom as a node contract: IN a figure crop → decide HOW figures
// are handled (classify per type, or OCR every figure) → HOW to classify (local heuristics / vision model /
// vision + heuristics) → the editable rules → the classes→branches OUT contract → the VLM connection (only
// when relevant). It edits the SAME flat config dict through the rail's per-field onChange; no new contract.

import { theme } from "../../../theme";
import { SegmentedControl } from "../../../components/SegmentedControl";
import { ClassRoutingChips } from "./ClassRoutingChips";
import { ClassifyRulesTable } from "./ClassifyRulesTable";
import { ClassifyVlmAdvanced } from "./ClassifyVlmAdvanced";
import {
  applyMethod, deriveMethod, deriveMode, heuristicsApply, usesVlm,
  type ClassifyMethod, type EnrichMode,
} from "./enrichClassifyModel";

interface EnrichClassifyPanelProps {
  config: Record<string, unknown>;
  onChange: (field: string, value: unknown) => void;
}

const contractChipStyle: React.CSSProperties = {
  fontFamily: theme.font.mono,
  fontSize: theme.font.size.xs, color: theme.color.dim,
  background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.s, padding: `2px ${theme.space.s}px`,
};

export function EnrichClassifyPanel({ config, onChange }: EnrichClassifyPanelProps) {
  const mode = deriveMode(config);
  const method = deriveMethod(config);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      {/* Node contract — the graph identity of this step. */}
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, flexWrap: "wrap" }}>
        <span style={contractChipStyle}>IN · figure crop</span>
        <span aria-hidden style={{ color: theme.color.mute }}>→</span>
        <span style={contractChipStyle}>OUT · enriched IR (kind + text/description)</span>
      </div>

      <SegmentedControl<EnrichMode>
        legend="How are figures handled?"
        value={mode}
        onChange={(v) => onChange("figure_enrich_mode", v)}
        options={[
          { value: "classified", label: "Classify, then enrich per type", description: "Sort each figure into a class, then OCR / describe it accordingly." },
          { value: "ocr_only", label: "OCR every figure — no classification", description: "Skip classification entirely; run one OCR chain over every figure (fully local)." },
        ]}
      />

      {mode === "ocr_only" ? (
        <div
          style={{
            background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.m, padding: theme.space.m, fontSize: theme.font.size.s,
            color: theme.color.dim, lineHeight: 1.5,
          }}
        >
          Every detected figure runs the <strong style={{ color: theme.color.text }}>OCR chain</strong> below — no
          classification, no vision model. Edit that chain to pick the local reader(s).
        </div>
      ) : (
        <>
          <SegmentedControl<ClassifyMethod>
            legend="How to classify each figure?"
            value={method}
            stack
            onChange={(v) => applyMethod(v, onChange)}
            options={[
              { value: "heuristics", label: "Local heuristics only", description: "Fully offline — geometry + on-device text density. No endpoint, no cost." },
              { value: "vlm", label: "Vision model (VLM)", description: "Ask a vision model for every figure's class." },
              { value: "vlm_heuristics", label: "Vision model + heuristics for obvious cases", description: "Decide the obvious cases locally first, ask the vision model only for the rest." },
            ]}
          />

          {heuristicsApply(method) && <ClassifyRulesTable config={config} method={method} onChange={onChange} />}

          <ClassRoutingChips />

          {usesVlm(method) && <ClassifyVlmAdvanced config={config} onChange={onChange} />}
        </>
      )}
    </div>
  );
}
