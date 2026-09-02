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
  // lineStrong, not line — line is near-invisible against surface2 on ink (~1.1:1); matches
  // SchemaField's own local inputStyle copy.
  border: `1px solid ${theme.color.lineStrong}`,
  borderRadius: theme.radius.m,
  padding: `${theme.space.xs + 2}px ${theme.space.s}px`,
  fontSize: theme.font.size.m,
  width: "100%",
};

interface MaxFileSizeFieldProps {
  valueMb: number;
  onChange: (mb: number) => void;
  /** Shares the wizard's own "Show technical details" state — see `SchemaForm`'s `advanced` prop. */
  advanced?: boolean;
}

export function MaxFileSizeField({ valueMb, onChange, advanced = false }: MaxFileSizeFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.size.s }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs + 2, color: theme.color.dim }}>
        {/* `NumberField` has no `id` passthrough today (see its prop surface), so a true
            `htmlFor`/`id` pairing isn't wireable from here without changing that shared primitive
            (out of this pass's scope — flagged for the primitives owner). The visible text below
            stays a plain `<span>` (a `<label>` with a `htmlFor` pointing at nothing would be a
            worse a11y regression than no association at all) — the control's real accessible name
            comes from the `ariaLabel` passed to `NumberField` below instead. */}
        <span style={{ color: theme.color.text }}>
          Max file size
          <span style={{ color: theme.color.error }} title="required"> *</span>
        </span>
        {advanced && (
          <span
            title="integer >= 1"
            style={{
              color: theme.color.mute, background: "transparent",
              border: `1px solid ${theme.color.line}`,
              borderRadius: theme.radius.s, padding: `0 ${theme.space.xs + 1}px`, fontSize: theme.font.size.xs,
              fontFamily: theme.font.mono, whiteSpace: "nowrap",
            }}
          >
            ≥ {MIN_MB}
          </span>
        )}
      </div>
      <NumberField
        value={valueMb}
        min={MIN_MB}
        style={inputStyle}
        suffix="MB"
        ariaLabel="Max file size in megabytes, required"
        onChange={(mb) => onChange(Math.max(MIN_MB, mb ?? MIN_MB))}
      />
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, lineHeight: 1.35 }}>
        Documents larger than this are rejected at upload.
      </div>
    </div>
  );
}
