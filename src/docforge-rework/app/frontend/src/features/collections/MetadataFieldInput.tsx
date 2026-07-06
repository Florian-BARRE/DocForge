// ====== Code Summary ======
// One declared-metadata control in the upload panel, generated from a single FieldSpec — the
// control shape follows field_type (+ enum_values when present), never a hardcoded per-field form.

import type { FieldSpec } from "../../api/collections";
import { FormField } from "../../components/FormField";
import { TagsInput } from "../../components/TagsInput";
import { inputStyle } from "../../components/inputStyle";

interface MetadataFieldInputProps {
  field: FieldSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

export function MetadataFieldInput({ field, value, onChange }: MetadataFieldInputProps) {
  const label = field.field_name + (field.required ? " *" : "");

  if (field.field_type === "bool")
    return (
      <FormField label={label}>
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} style={{ width: 16, height: 16 }} />
      </FormField>
    );

  if (field.field_type === "keyword_list")
    return (
      <FormField label={label}>
        <TagsInput values={(value as string[] | undefined) ?? []} onChange={onChange} />
      </FormField>
    );

  if (field.enum_values?.length)
    return (
      <FormField label={label}>
        <select style={inputStyle} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          <option value="" disabled>select…</option>
          {field.enum_values.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </FormField>
    );

  if (field.field_type === "integer" || field.field_type === "float")
    return (
      <FormField label={label}>
        <input
          type="number"
          step={field.field_type === "integer" ? 1 : "any"}
          style={inputStyle}
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        />
      </FormField>
    );

  if (field.field_type === "datetime")
    return (
      <FormField label={label} hint="Local time — sent as an ISO datetime string.">
        <input type="datetime-local" style={inputStyle} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
      </FormField>
    );

  return (
    <FormField label={label}>
      <input style={inputStyle} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    </FormField>
  );
}
