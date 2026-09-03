// ====== Code Summary ======
// A small on-brand segmented radiogroup: a row of mutually-exclusive options where the ONE active
// choice reads as the primary thing (forge accent), the rest at rest (steel/muted). Used to make a
// structural choice (a classification method, an enrich mode) look like the decision it is, instead
// of a bare dropdown buried in a form. Keyboard + aria handled; every option carries an optional
// one-line description rendered under the label.

import { theme } from "../theme";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  description?: string;
}

interface SegmentedControlProps<T extends string> {
  legend: string;
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  /** Stack vertically (for wordy options with descriptions) instead of a horizontal row. */
  stack?: boolean;
}

export function SegmentedControl<T extends string>({ legend, value, options, onChange, stack }: SegmentedControlProps<T>) {
  return (
    <fieldset style={{ border: "none", margin: 0, padding: 0, minInlineSize: "auto" }}>
      <legend
        style={{
          padding: 0, marginBottom: theme.space.xs, fontSize: theme.font.size.s,
          fontWeight: theme.font.weight.semibold, color: theme.color.text,
        }}
      >
        {legend}
      </legend>
      <div
        role="radiogroup"
        aria-label={legend}
        style={{ display: stack ? "flex" : "grid", flexDirection: "column",
          gridTemplateColumns: stack ? undefined : `repeat(${options.length}, 1fr)`, gap: theme.space.xs }}
      >
        {options.map((opt) => {
          const active = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(opt.value)}
              style={{
                textAlign: "left", cursor: "pointer",
                background: active ? theme.color.accentSoft : theme.color.surface,
                color: active ? theme.color.accentSafe : theme.color.text,
                border: `1px solid ${active ? theme.color.accentLine : theme.color.line}`,
                borderRadius: theme.radius.m, padding: `${theme.space.s}px ${theme.space.m}px`,
                display: "flex", flexDirection: "column", gap: 2,
              }}
            >
              <span style={{ fontSize: theme.font.size.m, fontWeight: theme.font.weight.semibold }}>{opt.label}</span>
              {opt.description && (
                <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim, lineHeight: 1.4 }}>
                  {opt.description}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
