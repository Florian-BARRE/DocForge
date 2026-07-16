// ====== Code Summary ======
// The metadata filter builder for the Search Lab: one compact input per filterable field of the
// collection (document- or chunk-scoped, user or generated), type-matched to `field_type`, plus a
// chip row echoing which filters are currently active. Renders nothing when the collection has no
// filterable field — filtering stays an obviously optional add-on, never a wall of inputs.

import type { FieldSpec, FieldType } from "../../api/collections";
import { Chip } from "../../components/Chip";
import { FormField } from "../../components/FormField";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";

interface SearchFilterBuilderProps {
  fields: FieldSpec[];
  values: Record<string, unknown>;
  onFilterChange: (fieldName: string, value: unknown | undefined) => void;
}

export function SearchFilterBuilder({ fields, values, onFilterChange }: SearchFilterBuilderProps) {
  if (fields.length === 0) return null;

  const activeEntries = Object.entries(values).filter(([, v]) => v !== undefined);

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        padding: theme.space.m, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, background: theme.color.card,
      }}
    >
      <span style={{ fontSize: theme.font.size.s, fontWeight: 600, color: theme.color.text }}>Filtres</span>

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.s }}>
        {fields.map((field) => (
          <div key={field.field_name} style={{ width: 160 }}>
            <FieldFilterControl
              field={field}
              value={values[field.field_name]}
              onChange={(v) => onFilterChange(field.field_name, v)}
            />
          </div>
        ))}
      </div>

      {activeEntries.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {activeEntries.map(([name, value]) => {
            const field = fields.find((f) => f.field_name === name);
            return (
              <Chip
                key={name}
                tone="accent"
                title="Cliquer pour retirer ce filtre"
              >
                <span style={{ cursor: "pointer" }} onClick={() => onFilterChange(name, undefined)}>
                  {name} = {formatFilterValue(field?.field_type, value)} ×
                </span>
              </Chip>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Human-readable rendering of an active filter's value, for the chip row. */
function formatFilterValue(fieldType: FieldType | undefined, value: unknown): string {
  if (fieldType === "bool") return value ? "oui" : "non";
  return String(value);
}

interface FieldFilterControlProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown | undefined) => void;
}

/** Renders the input matched to a single field's `field_type`, with omit-on-empty semantics. */
function FieldFilterControl({ field, value, onChange }: FieldFilterControlProps) {
  if (field.field_type === "enum") {
    return (
      <FormField label={field.field_name}>
        <select
          style={inputStyle}
          value={value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
        >
          <option value="">—</option>
          {(field.enum_values ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </FormField>
    );
  }

  if (field.field_type === "bool") {
    return (
      <FormField label={field.field_name}>
        <select
          style={inputStyle}
          value={value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value === "true")}
        >
          <option value="">—</option>
          <option value="true">oui</option>
          <option value="false">non</option>
        </select>
      </FormField>
    );
  }

  if (field.field_type === "integer" || field.field_type === "float") {
    return (
      <FormField label={field.field_name}>
        <input
          type="number"
          style={inputStyle}
          value={value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
        />
      </FormField>
    );
  }

  // Every remaining type (string/text/keyword_list/datetime/text_list/integer_list/float_list)
  // is filtered as a plain string.
  return (
    <FormField label={field.field_name}>
      <input
        type="text"
        style={inputStyle}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
      />
    </FormField>
  );
}
