// ====== Code Summary ======
// One JSON-Schema property rendered as the right control — enum → select, boolean → switch,
// number → numeric input, string → text (masked when the name smells like a secret) — with its
// full contract made visible: type (+ bounds / enum values), required flag, default, description.

import type { JsonSchema, JsonSchemaProperty } from "../../api/types";
import { theme } from "../../theme";

import { JsonField } from "./JsonField";
import { NumberField } from "./NumberField";

/** Pydantic hides enums behind $ref/$defs (sometimes wrapped in allOf) — inline them. */
export function deref(prop: JsonSchemaProperty, schema: JsonSchema): JsonSchemaProperty {
  const ref = prop.$ref ?? prop.allOf?.[0]?.$ref;
  if (!ref) return prop;
  const definition = schema.$defs?.[ref.split("/").pop() ?? ""] ?? {};
  return { ...definition, ...prop };
}

/** Human form of a property's type: "enum(a | b)", "number ≥ 0 ≤ 1", "string"… */
export function typeLabel(prop: JsonSchemaProperty): string {
  if (prop.enum) return prop.enum.join(" | ");
  let label = prop.type ?? "any";
  if (prop.minimum !== undefined) label += ` ≥ ${prop.minimum}`;
  if (prop.maximum !== undefined) label += ` ≤ ${prop.maximum}`;
  return label;
}


const inputStyle: React.CSSProperties = {
  background: theme.color.bg,
  border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.s,
  padding: "3px 6px",
  fontSize: theme.font.size.m,
  width: "100%",
};

interface SchemaFieldProps {
  name: string;
  prop: JsonSchemaProperty;
  schema: JsonSchema;
  value: unknown;
  required?: boolean;
  onChange: (value: unknown) => void;
}

export function SchemaField({ name, prop, schema, value, required = false, onChange }: SchemaFieldProps) {
  const resolved = deref(prop, schema);
  const current = value === undefined ? resolved.default : value;

  let control: JSX.Element;
  if (resolved.enum) {
    control = (
      <select style={inputStyle} value={String(current ?? "")} onChange={(e) => onChange(e.target.value)}>
        {resolved.enum.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    );
  } else if (resolved.type === "boolean") {
    control = (
      <input
        type="checkbox"
        checked={Boolean(current)}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 16, height: 16, accentColor: theme.color.accent }}
      />
    );
  } else if (resolved.type === "number" || resolved.type === "integer") {
    control = (
      <NumberField
        value={typeof current === "number" ? current : undefined}
        min={resolved.minimum}
        max={resolved.maximum}
        style={inputStyle}
        onChange={onChange}
      />
    );
  } else if (resolved.type === "array" || resolved.type === "object") {
    // Structured values get a real JSON editor — committed only when the JSON parses,
    // so an array field can never receive a raw string.
    control = (
      <JsonField
        value={current ?? (resolved.type === "array" ? [] : {})}
        onChange={onChange}
      />
    );
  } else {
    // A resizable textarea for EVERY string: short values stay one line, long values
    // (prompts, endpoints) can be dragged bigger via the native resize grip.
    const text = String(current ?? "");
    control = (
      <textarea
        rows={Math.min(6, Math.max(1, text.split("\n").length))}
        style={{ ...inputStyle, resize: "vertical", minHeight: 30, fontFamily: "inherit" }}
        value={text}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.size.s }}>
      {/* 1. Name + full type contract (+ required marker) */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, color: theme.color.dim }}>
        <span style={{ color: theme.color.text }}>
          {name}
          {required && <span style={{ color: theme.color.error }} title="required"> *</span>}
        </span>
        <span
          title={typeLabel(resolved)}
          style={{
            color: theme.color.warn, background: theme.color.warnSoft,
            borderRadius: theme.radius.s, padding: "0 4px", fontSize: theme.font.size.xs,
            fontFamily: theme.font.mono, whiteSpace: "nowrap", overflow: "hidden",
            textOverflow: "ellipsis", maxWidth: 130,
          }}
        >
          {typeLabel(resolved)}
        </span>
      </div>
      {/* 2. The control itself */}
      {control}
      {/* 3. Meaning + default, always visible (not a hover-only tooltip) */}
      {(resolved.description || resolved.default !== undefined) && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, lineHeight: 1.35 }}>
          {resolved.description}
          {resolved.default !== undefined && (
            <span style={{ color: theme.color.dim, opacity: 0.8 }}>
              {resolved.description ? " — " : ""}default: {String(resolved.default)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
