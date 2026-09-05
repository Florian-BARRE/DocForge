// ====== Code Summary ======
// The metadata filter builder for the Search Lab: one compact input per filterable field of the
// collection (document- or chunk-scoped, user or generated), type-matched to `field_type`, plus a
// chip row echoing which filters are currently active. Renders nothing when the collection has no
// filterable field — filtering stays an obviously optional add-on, never a wall of inputs.

import type { FieldSpec, FieldType } from "../../api/collections";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";
import { FilterValueControl } from "./FilterValueControl";
import type { RangeValue } from "./filterValue";

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
        borderRadius: theme.radius.l, background: theme.color.surface,
      }}
    >
      <span style={{ fontSize: theme.font.size.s, fontWeight: 600, color: theme.color.text }}>Filters</span>

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.s }}>
        {fields.map((field) => (
          <div key={field.field_name} style={{ minWidth: 160 }}>
            <FilterValueControl
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
                tone="capability"
                title="Click to remove this filter"
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

/** Human-readable rendering of an active filter's value, for the chip row — echoes the operator
 *  (any-of / range) rather than just `String(value)`, now that a value may be an array or a
 *  {gte/gt/lte/lt} mapping. */
function formatFilterValue(fieldType: FieldType | undefined, value: unknown): string {
  if (fieldType === "bool") return value ? "yes" : "no";
  if (Array.isArray(value)) return `any of ${value.join(", ")}`;
  if (value !== null && typeof value === "object") {
    const range = value as RangeValue;
    const parts: string[] = [];
    if (range.gte !== undefined) parts.push(`≥ ${range.gte}`);
    if (range.gt !== undefined) parts.push(`> ${range.gt}`);
    if (range.lte !== undefined) parts.push(`≤ ${range.lte}`);
    if (range.lt !== undefined) parts.push(`< ${range.lt}`);
    return parts.join(" and ") || "any";
  }
  return String(value);
}
