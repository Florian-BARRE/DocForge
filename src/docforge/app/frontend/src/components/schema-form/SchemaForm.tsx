// ====== Code Summary ======
// Generic JSON-Schema form — the rendering engine that makes any backend-described config
// editable with zero per-node frontend code. Shared by every config surface (stage rail cards, the
// collection wizard's Identity step). Two humanization affordances live here, on top of what
// `SchemaField` already does per-property: a "Show technical details" toggle — REAL progressive
// disclosure, not just a badge — that hides numeric tuning fields (`isAdvancedField`) until
// toggled on, and a "JSON" escape hatch that swaps the whole form for one raw-JSON editor bound to
// the same values.

import { useState } from "react";

import type { JsonSchema, JsonSchemaProperty } from "../../api/types";
import { theme } from "../../theme";
import { isAdvancedField } from "./advancedFields";
import { JsonField } from "./JsonField";
import { deref, SchemaField } from "./SchemaField";

interface SchemaFormProps {
  schema: JsonSchema;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  columns?: number;
  /** Lets a parent that renders its own extra fields alongside this form (the wizard's
   *  `MaxFileSizeField`) share ONE "Show technical details" state instead of each control owning
   *  its own toggle. Omit for the normal, self-contained case — every other caller today. */
  advanced?: boolean;
  onAdvancedChange?: (advanced: boolean) => void;
  /** Same sharing pattern as `advanced`, for the JSON escape hatch — lets a parent that renders its
   *  own dedicated widget for one of this form's values (the wizard's `MaxFileSizeField`, mirroring
   *  `max_file_size_bytes`) hide that widget while JSON view is active, so the value never has TWO
   *  live editors at once. Omit for the normal, self-contained case. */
  jsonMode?: boolean;
  onJsonModeChange?: (jsonMode: boolean) => void;
}

const toggleButtonStyle = (active: boolean): React.CSSProperties => ({
  background: active ? theme.color.accentSoft : "transparent",
  color: active ? theme.color.accent : theme.color.dim,
  border: `1px solid ${active ? theme.color.accentLine : theme.color.line}`,
  borderRadius: theme.radius.pill,
  padding: "3px 10px",
  fontSize: theme.font.size.xs,
  fontWeight: theme.font.weight.semibold,
  cursor: "pointer",
});

export function SchemaForm({
  schema, values, onChange, columns = 2, advanced, onAdvancedChange, jsonMode, onJsonModeChange,
}: SchemaFormProps) {
  const properties = Object.entries(schema.properties ?? {});
  // Falls back to local state when the parent doesn't share its own (the common, self-contained
  // case) — every existing call site keeps working with zero changes.
  const [localAdvanced, setLocalAdvanced] = useState(false);
  const isAdvanced = advanced ?? localAdvanced;
  const setAdvanced = onAdvancedChange ?? setLocalAdvanced;
  const [localJsonMode, setLocalJsonMode] = useState(false);
  const isJsonMode = jsonMode ?? localJsonMode;
  const setJsonMode = onJsonModeChange ?? setLocalJsonMode;

  if (!properties.length) return null;
  const required = new Set(schema.required ?? []);

  // The basic/advanced split, computed once per render off the schema itself — see
  // `isAdvancedField`'s doc for the exact heuristic. `basicProps` are ALWAYS rendered; `advancedProps`
  // only when the toggle is on, and the toggle button itself only exists when there is something to
  // hide (an all-basic schema, e.g. a pure method picker, never grows a dead "hides nothing" button).
  const basicProps = properties.filter(([name, prop]) => !isAdvancedField(name, deref(prop, schema)));
  const advancedProps = properties.filter(([name, prop]) => isAdvancedField(name, deref(prop, schema)));
  const hasAdvancedFields = advancedProps.length > 0;

  const renderField = ([name, prop]: [string, JsonSchemaProperty]) => (
    <SchemaField
      key={name}
      name={name}
      prop={prop}
      schema={schema}
      value={values[name]}
      required={required.has(name)}
      advanced={isAdvanced}
      onChange={(value) => onChange(name, value)}
    />
  );

  // Translates one whole-object edit from the JSON escape hatch into the same per-key `onChange`
  // every control here already uses — a key missing from the new object is explicitly unset
  // (`undefined`, not deleted from the call signature) so an optional field can be cleared this way.
  const applyJsonEdit = (next: unknown) => {
    const nextObject = next && typeof next === "object" && !Array.isArray(next) ? (next as Record<string, unknown>) : {};
    for (const key of Object.keys(nextObject)) onChange(key, nextObject[key]);
    for (const key of Object.keys(values)) if (!(key in nextObject)) onChange(key, undefined);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: theme.space.xs }}>
        {!isJsonMode && hasAdvancedFields && (
          <button type="button" style={toggleButtonStyle(isAdvanced)} onClick={() => setAdvanced(!isAdvanced)}>
            {isAdvanced ? "Hide technical details" : "Show technical details"}
          </button>
        )}
        <button type="button" style={toggleButtonStyle(isJsonMode)} onClick={() => setJsonMode(!isJsonMode)}>
          {isJsonMode ? "Form view" : "JSON view"}
        </button>
      </div>
      {isJsonMode ? (
        <JsonField value={values} onChange={applyJsonEdit} />
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: "10px 10px" }}>
            {basicProps.map(renderField)}
          </div>
          {hasAdvancedFields && isAdvanced && (
            <div
              style={{
                display: "grid", gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: "10px 10px",
                marginTop: theme.space.xs, paddingTop: theme.space.s, borderTop: `1px solid ${theme.color.line}`,
              }}
            >
              {advancedProps.map(renderField)}
            </div>
          )}
        </>
      )}
    </div>
  );
}
