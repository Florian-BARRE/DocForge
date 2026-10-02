// ====== Code Summary ======
// One row of the metadata editor: field name + origin/surface chips, the schema-driven control, the
// "overwritten on next reingest" hint for GENERATED fields, and the inline per-field error.

import { useId } from "react";
import type { FieldSpec } from "../../../../api/collections";
import { Chip } from "../../../../components/Chip";
import { theme } from "../../../../theme";
import { MetadataEditControl } from "./MetadataEditControl";

interface MetadataEditFieldProps {
  field: FieldSpec;
  value: unknown;
  error?: string;
  onChange: (value: unknown) => void;
}

export function MetadataEditField({ field, value, error, onChange }: MetadataEditFieldProps) {
  const controlId = useId();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <label htmlFor={controlId} style={{ display: "flex", alignItems: "center", gap: theme.space.s, fontSize: theme.font.size.s }}>
        <span style={{ color: theme.color.text, fontWeight: theme.font.weight.semibold }}>{field.field_name}</span>
        <Chip tone={field.origin === "generated" ? "loop" : "dim"}>{field.origin}</Chip>
      </label>
      <div style={error ? { outline: `1px solid ${theme.color.error}`, borderRadius: theme.radius.m } : undefined}>
        <MetadataEditControl field={field} value={value} onChange={onChange} id={controlId} />
      </div>
      {error && <span role="alert" style={{ color: theme.color.errorStrong, fontSize: theme.font.size.xs }}>{error}</span>}
      {field.origin === "generated" && (
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>
          Generated field — a manual value is overwritten on the next reingest or metadata generation.
        </span>
      )}
    </div>
  );
}
