// ====== Code Summary ======
// One labelled config input (text or number) with an inline help line — the shared field primitive of
// the enrich-classify panel, used for both the heuristic thresholds and the VLM connection fields. A
// plain, on-brand, accessible input (label + <input> tied by id); numeric values are coerced on change.

import { useId } from "react";

import { theme } from "../../../theme";

interface LabeledInputProps {
  label: string;
  help?: string;
  value: string | number;
  onChange: (value: string) => void;
  type?: "text" | "number";
  suffix?: string;
  min?: number;
  max?: number;
  step?: number;
  mono?: boolean;
  placeholder?: string;
}

export function LabeledInput({
  label, help, value, onChange, type = "text", suffix, min, max, step, mono, placeholder,
}: LabeledInputProps) {
  const id = useId();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <label htmlFor={id} style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.medium, color: theme.color.text }}>
        {label}
      </label>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
        <input
          id={id}
          type={type}
          value={value}
          min={min}
          max={max}
          step={step}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          style={{
            flex: 1, minWidth: 0,
            background: theme.color.surface, color: theme.color.text,
            border: `1px solid ${theme.color.lineStrong}`, borderRadius: theme.radius.s,
            padding: `${theme.space.xs}px ${theme.space.s}px`, fontSize: theme.font.size.m,
            fontFamily: mono ? theme.font.mono : theme.font.family,
          }}
        />
        {suffix && <span style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>{suffix}</span>}
      </div>
      {help && <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim, lineHeight: 1.4 }}>{help}</span>}
    </div>
  );
}
