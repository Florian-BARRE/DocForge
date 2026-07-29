// ====== Code Summary ======
// One declared-metadata control in the upload panel, generated from a single FieldSpec — the
// control shape follows field_type (+ enum_values when present), never a hardcoded per-field form.

import type { FieldSpec } from "../../api/collections";
import { FormField } from "../../components/FormField";
import { NumberField } from "../../components/schema-form/NumberField";
import { Switch } from "../../components/Switch";
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
        <Switch checked={Boolean(value)} onChange={onChange} />
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
        <NumberField
          value={value as number | undefined}
          style={inputStyle}
          onChange={onChange}
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
