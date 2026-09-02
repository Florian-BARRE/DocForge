// ====== Code Summary ======
// Numeric config field with a local string draft (mirrors JsonField's pattern) — an in-progress
// edit like an emptied input or a bare "-" never round-trips through `Number()` and commits as 0.
// The draft only commits once it parses to a real number; clearing the field commits `undefined`
// (the field is omitted from the config, letting the backend default apply) instead of `0`.

import { useEffect, useState } from "react";

import { theme } from "../../theme";

export interface NumberFieldProps {
  /** The current (committed) value from the config. */
  value: number | undefined;
  min?: number;
  max?: number;
  style: React.CSSProperties;
  /** Called with the parsed number, or `undefined` when the field is cleared. */
  onChange: (value: number | undefined) => void;
  /** Accessible name — only needed when the field has no visible/associated `<label>`. */
  ariaLabel?: string;
  /** A short unit adornment rendered right after the input (e.g. "MB", "seconds") — the unit is
   *  MEANING, not a technical detail, so it's always visible, never gated behind an "advanced"
   *  toggle. Omit for unitless numbers (counts, ratios). */
  suffix?: string;
}

export function NumberField({ value, min, max, style, onChange, ariaLabel, suffix }: NumberFieldProps) {
  const [draft, setDraft] = useState(value === undefined || value === null ? "" : String(value));
  const [focused, setFocused] = useState(false);

  // Resync from the outside (stage switch, a settling debounced apply) only when the user is not
  // typing — otherwise every committed edit would reformat the text under the cursor.
  useEffect(() => {
    if (!focused) setDraft(value === undefined || value === null ? "" : String(value));
  }, [value, focused]);

  const handleChange = (text: string) => {
    setDraft(text);
    if (text.trim() === "") {
      onChange(undefined);
      return;
    }
    const parsed = Number(text);
    if (!Number.isNaN(parsed)) onChange(parsed);
  };

  const input = (
    <input
      type="number"
      step="any"
      min={min}
      max={max}
      style={suffix ? { ...style, width: "100%" } : style}
      value={draft}
      aria-label={ariaLabel}
      onChange={(e) => handleChange(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    />
  );

  if (!suffix) return input;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
      {input}
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.s, whiteSpace: "nowrap" }}>{suffix}</span>
    </div>
  );
}
