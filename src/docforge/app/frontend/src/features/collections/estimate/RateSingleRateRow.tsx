// ====== Code Summary ======
// One embed-model or OCR-provider editable price row — a single USD rate, unlike a chat model's
// paired input/output (see RateModelRow). "Reset" clears it back to "use the default rate".

import { Button } from "../../../components/Button";
import { NumberField } from "../../../components/schema-form/NumberField";
import { theme } from "../../../theme";

interface RateSingleRateRowProps {
  label: string;
  unit: string;
  value: number | undefined;
  onChange: (value: number | undefined) => void;
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

export function RateSingleRateRow({ label, unit, value, onChange }: RateSingleRateRowProps) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 120px auto", alignItems: "center", gap: theme.space.s }}>
      <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.text, wordBreak: "break-all" }}>{label}</span>
      <NumberField value={value} min={0} suffix={unit} ariaLabel={`${label} price`} style={FIELD_STYLE} onChange={onChange} />
      <Button size="sm" variant="ghost" onClick={() => onChange(undefined)}>Reset</Button>
    </div>
  );
}
