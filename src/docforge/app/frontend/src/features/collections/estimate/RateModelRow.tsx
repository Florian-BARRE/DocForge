// ====== Code Summary ======
// One chat/LLM/VLM model's editable (input, output) price row. Both halves are independently
// draftable (see estimateOverridesDraft.ts) — only a fully-filled row is sent as an override, a
// "Reset" clears both at once back to "use the default rate".

import { Button } from "../../../components/Button";
import { NumberField } from "../../../components/schema-form/NumberField";
import { theme } from "../../../theme";
import type { ModelRateDraft } from "./estimateOverridesDraft";

interface RateModelRowProps {
  modelId: string;
  value: ModelRateDraft;
  onChange: (value: ModelRateDraft) => void;
}

const FIELD_STYLE: React.CSSProperties = {
  background: theme.color.surface2,
  border: `1px solid ${theme.color.lineStrong}`,
  borderRadius: theme.radius.m,
  padding: "5px 8px",
  fontSize: theme.font.size.m,
  color: theme.color.text,
  width: "100%",
};

export function RateModelRow({ modelId, value, onChange }: RateModelRowProps) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 120px auto", alignItems: "center", gap: theme.space.s }}>
      <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.text, wordBreak: "break-all" }}>{modelId}</span>
      <NumberField
        value={value.input}
        min={0}
        suffix="in/1M"
        ariaLabel={`${modelId} input price per 1M tokens`}
        style={FIELD_STYLE}
        onChange={(input) => onChange({ ...value, input })}
      />
      <NumberField
        value={value.output}
        min={0}
        suffix="out/1M"
        ariaLabel={`${modelId} output price per 1M tokens`}
        style={FIELD_STYLE}
        onChange={(output) => onChange({ ...value, output })}
      />
      <Button size="sm" variant="ghost" onClick={() => onChange({})}>Reset</Button>
    </div>
  );
}
