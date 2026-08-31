// ====== Code Summary ======
// A dedicated MB-labeled control for the contract's `max_file_size_bytes` field — excluded from
// the generic `SchemaForm` render (see `StepIdentity`) because every other surface in the app
// (Review step, collection header) shows this limit in MB, but the schema-driven number input
// would otherwise render the raw byte integer with no unit conversion. Mirrors `SchemaField`'s
// layout so it reads as part of the same form, not a bolted-on control.

import { NumberField } from "../../../components/schema-form/NumberField";
import { theme } from "../../../theme";

const MIN_MB = 1;

const inputStyle: React.CSSProperties = {
  background: theme.color.surface2,
  color: theme.color.text,
  border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.m,
  padding: `${theme.space.xs + 2}px ${theme.space.s}px`,
  fontSize: theme.font.size.m,
  width: "100%",
};

interface MaxFileSizeFieldProps {
  valueMb: number;
  onChange: (mb: number) => void;
}

export function MaxFileSizeField({ valueMb, onChange }: MaxFileSizeFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.size.s }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs + 2, color: theme.color.dim }}>
        <span style={{ color: theme.color.text }}>
          Max file size
          <span style={{ color: theme.color.error }} title="required"> *</span>
        </span>
        <span
          title="integer >= 1"
          style={{
            color: theme.color.mute, background: "transparent",
            border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.s, padding: `0 ${theme.space.xs + 1}px`, fontSize: theme.font.size.xs,
            fontFamily: theme.font.mono, whiteSpace: "nowrap",
          }}
        >
          MB ≥ {MIN_MB}
        </span>
      </div>
      <NumberField
        value={valueMb}
        min={MIN_MB}
        style={inputStyle}
        onChange={(mb) => onChange(Math.max(MIN_MB, mb ?? MIN_MB))}
      />
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, lineHeight: 1.35 }}>
        Upload size ceiling. Sent to the backend as bytes (contract field <code>max_file_size_bytes</code>).
      </div>
    </div>
  );
}
