// ====== Code Summary ======
// Generic JSON-Schema form — the rendering engine that makes any backend-described config
// editable with zero per-node frontend code. Shared by every config surface (stage rail cards).

import type { JsonSchema } from "../../api/types";
import { SchemaField } from "./SchemaField";

interface SchemaFormProps {
  schema: JsonSchema;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  columns?: number;
}

export function SchemaForm({ schema, values, onChange, columns = 2 }: SchemaFormProps) {
  const properties = Object.entries(schema.properties ?? {});
  if (!properties.length) return null;
  const required = new Set(schema.required ?? []);
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: "10px 10px" }}>
      {properties.map(([name, prop]) => (
        <SchemaField
          key={name}
          name={name}
          prop={prop}
          schema={schema}
          value={values[name]}
          required={required.has(name)}
          onChange={(value) => onChange(name, value)}
        />
      ))}
    </div>
  );
}
