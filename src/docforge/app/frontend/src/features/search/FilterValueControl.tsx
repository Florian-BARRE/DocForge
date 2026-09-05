// ====== Code Summary ======
// The per-field filter editor behind SearchFilterBuilder: an operator switch (is / is any of /
// range) plus the value editor matched to it, so the user can construct exactly the shapes the
// wire contract accepts — a scalar, a list (any-of), or a {gte/gt/lte/lt} range mapping (see
// filterValue.ts). The three value editors are small, only ever rendered together for one field,
// and share no state beyond the field/value/onChange props — kept in this one file per the
// grouped-primitives exception to one-component-per-file.

import { useState } from "react";
import type { FieldSpec } from "../../api/collections";
import { FormField } from "../../components/FormField";
import { inputStyle } from "../../components/inputStyle";
import { TagsInput } from "../../components/TagsInput";
import { theme } from "../../theme";
import { cleanRange, isNumericFieldType, modeOfValue, modesForFieldType, type FilterMode, type RangeValue } from "./filterValue";

interface FilterValueControlProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown | undefined) => void;
}

const MODE_LABEL: Record<FilterMode, string> = { eq: "is", any: "is any of", range: "range" };

const modeSelectStyle: React.CSSProperties = {
  ...inputStyle, fontSize: theme.font.size.xs, padding: "4px 8px", marginBottom: 4,
};

export function FilterValueControl({ field, value, onChange }: FilterValueControlProps) {
  const modes = modesForFieldType(field.field_type);
  const [mode, setMode] = useState<FilterMode>(() => (value === undefined ? "eq" : modeOfValue(value)));

  // Switching operator clears the half-built value instead of coercing it — a string typed for
  // "is" is not a sensible any-of/range seed, and guessing would risk sending a malformed filter.
  const handleModeChange = (next: FilterMode) => {
    setMode(next);
    onChange(undefined);
  };

  return (
    <FormField label={field.field_name}>
      {modes.length > 1 && (
        <select
          style={modeSelectStyle}
          value={mode}
          onChange={(e) => handleModeChange(e.target.value as FilterMode)}
          aria-label={`${field.field_name} filter operator`}
        >
          {modes.map((m) => (
            <option key={m} value={m}>{MODE_LABEL[m]}</option>
          ))}
        </select>
      )}
      {mode === "eq" && <EqControl field={field} value={value} onChange={onChange} />}
      {mode === "any" && <AnyControl field={field} value={value} onChange={onChange} />}
      {mode === "range" && <RangeControl field={field} value={value as RangeValue | undefined} onChange={onChange} />}
    </FormField>
  );
}

/** Exact-match editor — one control per field_type, unchanged from the original builder. */
function EqControl({ field, value, onChange }: FilterValueControlProps) {
  if (field.field_type === "enum") {
    return (
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
    );
  }

  if (field.field_type === "bool") {
    return (
      <select
        style={inputStyle}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value === "true")}
      >
        <option value="">—</option>
        <option value="true">yes</option>
        <option value="false">no</option>
      </select>
    );
  }

  if (field.field_type === "datetime") {
    return (
      <input
        type="date"
        style={inputStyle}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
      />
    );
  }

  if (isNumericFieldType(field.field_type)) {
    return (
      <input
        type="number"
        style={inputStyle}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      />
    );
  }

  return (
    <input
      type="text"
      style={inputStyle}
      value={value === undefined ? "" : String(value)}
      onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
    />
  );
}

const enumChipStyle = (active: boolean): React.CSSProperties => ({
  cursor: "pointer", border: `1px solid ${active ? theme.color.accentLine : theme.color.line}`,
  background: active ? theme.color.accentSoft : theme.color.surface2,
  color: active ? theme.color.accentSafe : theme.color.dim,
  borderRadius: theme.radius.pill, padding: "2px 9px", fontSize: theme.font.size.xs, fontWeight: 600,
});

/** Any-of editor — a toggle-chip list for a closed enum, a free-form tag list otherwise. */
function AnyControl({ field, value, onChange }: FilterValueControlProps) {
  if (field.field_type === "enum") {
    const selected = Array.isArray(value) ? (value as string[]) : [];
    const options = field.enum_values ?? [];
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {options.map((option) => {
          const active = selected.includes(option);
          return (
            <button
              key={option}
              type="button"
              onClick={() => {
                const next = active ? selected.filter((v) => v !== option) : [...selected, option];
                onChange(next.length > 0 ? next : undefined);
              }}
              style={enumChipStyle(active)}
            >
              {option}
            </button>
          );
        })}
      </div>
    );
  }

  const numeric = isNumericFieldType(field.field_type);
  const tags = Array.isArray(value) ? (value as (string | number)[]).map(String) : [];
  return (
    <TagsInput
      values={tags}
      onChange={(next) => {
        if (next.length === 0) {
          onChange(undefined);
          return;
        }
        onChange(numeric ? next.map(Number).filter((n) => !Number.isNaN(n)) : next);
      }}
      placeholder="value, value…"
      ariaLabel={`${field.field_name} any-of values`}
    />
  );
}

type BoundKey = keyof RangeValue;
const boundSelectStyle: React.CSSProperties = {
  ...inputStyle, fontSize: theme.font.size.xs, padding: "4px 6px", width: "auto",
};

/** Range editor — a lower (gte/gt) and upper (lte/lt) bound, each with its own inclusive toggle. */
function RangeControl({ field, value, onChange }: { field: FieldSpec; value: RangeValue | undefined; onChange: (v: unknown | undefined) => void }) {
  const range = value ?? {};
  const inputType = field.field_type === "datetime" ? "date" : "number";
  const lowerKey: BoundKey = range.gt !== undefined ? "gt" : "gte";
  const upperKey: BoundKey = range.lt !== undefined ? "lt" : "lte";

  const setBoundKey = (current: BoundKey, next: BoundKey, other: BoundKey) => {
    const draft: RangeValue = { ...range };
    if (current !== next && draft[current] !== undefined) {
      draft[next] = draft[current];
      delete draft[current];
    }
    delete draft[other];
    onChange(cleanRange(draft));
  };

  const setBoundValue = (key: BoundKey, raw: string) => {
    const draft: RangeValue = { ...range };
    if (raw === "") delete draft[key];
    else draft[key] = inputType === "date" ? raw : Number(raw);
    onChange(cleanRange(draft));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", gap: 4 }}>
        <select
          style={boundSelectStyle}
          value={lowerKey}
          onChange={(e) => setBoundKey(lowerKey, e.target.value as BoundKey, e.target.value === "gte" ? "gt" : "gte")}
          aria-label={`${field.field_name} lower-bound operator`}
        >
          <option value="gte">≥</option>
          <option value="gt">&gt;</option>
        </select>
        <input
          type={inputType}
          style={inputStyle}
          value={range[lowerKey] === undefined ? "" : String(range[lowerKey])}
          onChange={(e) => setBoundValue(lowerKey, e.target.value)}
          aria-label={`${field.field_name} lower bound`}
        />
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        <select
          style={boundSelectStyle}
          value={upperKey}
          onChange={(e) => setBoundKey(upperKey, e.target.value as BoundKey, e.target.value === "lte" ? "lt" : "lte")}
          aria-label={`${field.field_name} upper-bound operator`}
        >
          <option value="lte">≤</option>
          <option value="lt">&lt;</option>
        </select>
        <input
          type={inputType}
          style={inputStyle}
          value={range[upperKey] === undefined ? "" : String(range[upperKey])}
          onChange={(e) => setBoundValue(upperKey, e.target.value)}
          aria-label={`${field.field_name} upper bound`}
        />
      </div>
    </div>
  );
}
