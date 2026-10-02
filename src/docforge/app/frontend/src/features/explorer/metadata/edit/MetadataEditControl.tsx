// ====== Code Summary ======
// The input for one editable metadata value — the control shape follows the field's schema type
// (string → text, integer/float → number, bool → the brand switch, enum → select, *_list → tags,
// datetime → local datetime). Never a hardcoded per-field form.

import type { FieldSpec } from "../../../../api/collections";
import { inputStyle } from "../../../../components/inputStyle";
import { NumberField } from "../../../../components/schema-form/NumberField";
import { Switch } from "../../../../components/Switch";
import { TagsInput } from "../../../../components/TagsInput";

interface MetadataEditControlProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  id: string;
}

const NUMERIC_LIST_TYPES = ["integer_list", "float_list"];
const LIST_TYPES = ["keyword_list", "text_list", ...NUMERIC_LIST_TYPES];
// datetime-local needs "YYYY-MM-DDTHH:mm" — the stored ISO string is trimmed for display only.
const DATETIME_LOCAL_LENGTH = 16;

function asList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

export function MetadataEditControl({ field, value, onChange, id }: MetadataEditControlProps) {
  const type = field.field_type;

  if (type === "bool") return <Switch id={id} checked={Boolean(value)} onChange={onChange} />;

  if (LIST_TYPES.includes(type)) {
    const numeric = NUMERIC_LIST_TYPES.includes(type);
    return (
      <TagsInput
        id={id}
        values={asList(value)}
        onChange={(next) => onChange(numeric ? next.map(Number).filter((n) => !Number.isNaN(n)) : next)}
      />
    );
  }

  if (field.enum_values?.length)
    return (
      <select id={id} style={inputStyle} value={value == null ? "" : String(value)} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">—</option>
        {field.enum_values.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    );

  if (type === "integer" || type === "float")
    return <NumberField id={id} value={typeof value === "number" ? value : undefined} style={inputStyle} onChange={onChange} />;

  if (type === "datetime")
    return (
      <input
        id={id} type="datetime-local" style={inputStyle}
        value={typeof value === "string" ? value.slice(0, DATETIME_LOCAL_LENGTH) : ""}
        onChange={(e) => onChange(e.target.value || null)}
      />
    );

  return <input id={id} style={inputStyle} value={value == null ? "" : String(value)} onChange={(e) => onChange(e.target.value)} />;
}
