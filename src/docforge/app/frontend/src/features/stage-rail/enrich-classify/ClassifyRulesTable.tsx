// ====== Code Summary ======
// The classification RULES made tangible: a plain-language list of the cheap geometric cases the
// classifier decides before (or instead of) any model call, with the two thresholds editable INLINE so
// the user literally has their hand on what gets classified how. full_page_ratio is edited as a percent
// (stored as a 0–1 float); min_side_px as pixels. The "everything else" line names who decides the rest.

import { theme } from "../../../theme";
import { LabeledInput } from "./LabeledInput";
import { readNum, type ClassifyMethod } from "./enrichClassifyModel";

interface ClassifyRulesTableProps {
  config: Record<string, unknown>;
  method: ClassifyMethod;
  onChange: (field: string, value: unknown) => void;
}

export function ClassifyRulesTable({ config, method, onChange }: ClassifyRulesTableProps) {
  const fullPagePct = Math.round(readNum(config.full_page_ratio, 0.85) * 100);
  const minSide = readNum(config.min_side_px, 48);
  const elseDecider = method === "heuristics" ? "the local classifier (text density + shape)" : "the vision model";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <div style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, color: theme.color.text }}>
        Rules applied first (no model call)
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.m }}>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          <LabeledInput
            label="Full-page coverage →"
            help="A figure covering at least this much of the page is treated as a scanned page → OCR."
            type="number"
            min={1}
            max={100}
            suffix="% → scanned text"
            mono
            value={fullPagePct}
            onChange={(v) => {
              const pct = Number(v);
              if (Number.isFinite(pct)) onChange("full_page_ratio", Math.min(1, Math.max(0, pct / 100)));
            }}
          />
          <LabeledInput
            label="Tiny-crop cutoff →"
            help="Crops whose shortest side is under this are decorative (logos, rules) → skipped, no cost."
            type="number"
            min={1}
            suffix="px → decorative"
            mono
            value={minSide}
            onChange={(v) => {
              const px = Number(v);
              if (Number.isFinite(px) && px >= 1) onChange("min_side_px", Math.round(px));
            }}
          />
        </div>
        <div
          style={{
            alignSelf: "start", background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.m, padding: theme.space.m, fontSize: theme.font.size.s,
            color: theme.color.dim, lineHeight: 1.5,
          }}
        >
          Everything the rules don't decide → classified by <strong style={{ color: theme.color.text }}>{elseDecider}</strong>
          {" "}into one of the five classes below.
        </div>
      </div>
    </div>
  );
}
