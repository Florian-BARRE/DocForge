// ====== Code Summary ======
// The "assumptions" half of the overrides editor — one NumberField per extrapolation coefficient
// (ASSUMPTION_FIELDS), placeholder-seeded from the EFFECTIVE assumptions the last estimate run
// echoed back (so the placeholder is never an invented number — see api/collections.ts's
// EstimateOverrides doc). Clearing a field commits `undefined`, which the parent's PATCH omits —
// falling back to the default, exactly like NumberField's existing clear-to-unset convention.

import type { AssumptionOverrides } from "../../../api/collections";
import { NumberField } from "../../../components/schema-form/NumberField";
import { theme } from "../../../theme";
import { ASSUMPTION_FIELDS } from "./assumptionFields";

interface EstimateAssumptionsFormProps {
  values: AssumptionOverrides;
  /** The last run's effective assumptions (echoed by the estimate response), or `null` before any
   *  estimate has run yet — shown as each field's placeholder, never a guessed number. */
  placeholders: Record<string, unknown> | null;
  onChange: (key: keyof AssumptionOverrides, value: number | undefined) => void;
}

const NUMBER_FIELD_STYLE: React.CSSProperties = {
  background: theme.color.surface2,
  border: `1px solid ${theme.color.lineStrong}`,
  borderRadius: theme.radius.m,
  padding: "6px 9px",
  fontSize: theme.font.size.m,
  color: theme.color.text,
  width: "100%",
};

export function EstimateAssumptionsForm({ values, placeholders, onChange }: EstimateAssumptionsFormProps) {
  return (
    <div>
      <div style={{ fontSize: theme.font.size.s, color: theme.color.dim, marginBottom: theme.space.s }}>
        Fine-tune the coefficients the estimator extrapolates from. Leave a field blank to use the default
        {placeholders ? " (shown as its placeholder, from the last run)" : ""}.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: theme.space.m }}>
        {ASSUMPTION_FIELDS.map((field) => {
          const placeholderRaw = placeholders?.[field.key];
          const placeholder = typeof placeholderRaw === "number" ? String(placeholderRaw) : undefined;
          return (
            <label key={field.key} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: theme.font.size.s }}>
              <span style={{ color: theme.color.dim, fontWeight: theme.font.weight.semibold }}>{field.label}</span>
              <NumberField
                value={values[field.key] ?? undefined}
                placeholder={placeholder}
                min={field.min}
                max={field.max}
                suffix={field.suffix}
                ariaLabel={field.label}
                style={NUMBER_FIELD_STYLE}
                onChange={(value) => onChange(field.key, value)}
              />
              <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>{field.hint}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
