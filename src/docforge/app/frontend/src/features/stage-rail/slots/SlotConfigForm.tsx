// ====== Code Summary ======
// The config form of one slot's selected provider — rendered by the shared schema-driven SchemaForm
// from `config_schemas[provider]`, so a new backend field surfaces here with zero frontend edit.
// The `kind` discriminator is dropped (the picker owns it); secrets arrive masked and are only ever
// sent when re-typed (the edit is a `merge` of the touched keys).

import { useMemo } from "react";
import { SchemaForm } from "../../../components/schema-form/SchemaForm";
import type { JsonSchema, ProviderSlotView, ValidationIssue } from "../../../api/types";
import { theme } from "../../../theme";

interface SlotConfigFormProps {
  slotView: ProviderSlotView;
  onChange: (field: string, value: unknown) => void;
  issues?: ValidationIssue[];
}

function withoutKind(schema: JsonSchema): JsonSchema {
  const { kind: _kind, ...properties } = schema.properties ?? {};
  return { ...schema, properties };
}

export function SlotConfigForm({ slotView, onChange, issues }: SlotConfigFormProps) {
  const schema = slotView.provider ? (slotView.config_schemas[slotView.provider] as JsonSchema | undefined) : undefined;
  const formSchema = useMemo(() => (schema ? withoutKind(schema) : null), [schema]);
  if (!formSchema || !slotView.config) return null;
  const hasKeyAndUrl = "api_key" in (formSchema.properties ?? {}) && "base_url" in (formSchema.properties ?? {});
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <SchemaForm schema={formSchema} values={slotView.config} onChange={onChange} issues={issues} />
      {hasKeyAndUrl && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          The stored key stays masked and is kept as is. Changing the base URL requires re-entering the key.
        </div>
      )}
    </div>
  );
}
