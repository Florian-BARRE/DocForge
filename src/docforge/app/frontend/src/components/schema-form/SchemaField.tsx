// ====== Code Summary ======
// One JSON-Schema property rendered as the right control — enum → select, boolean → switch,
// number → numeric input, string → text (masked when the name smells like a secret) — with its
// full contract made visible: type (+ bounds / enum values), required flag, default, description.

import type { JsonSchema, JsonSchemaProperty } from "../../api/types";
import { Switch } from "../Switch";
import { TagsInput } from "../TagsInput";
import { theme } from "../../theme";

import { JsonField } from "./JsonField";
import { NumberField } from "./NumberField";

/**
 * Pydantic hides enums behind $ref/$defs (sometimes wrapped in allOf) — inline them. Also
 * collapses the `X | None` shape (serialized as `anyOf: [{...X}, {type:"null"}]`) down to the
 * non-null branch, so every other control only ever has to reason about the plain typed/enum
 * property — see `SchemaField`'s own `nullable` flag for the corresponding "can be unset" case.
 */
export function deref(prop: JsonSchemaProperty, schema: JsonSchema): JsonSchemaProperty {
  let resolved = prop;
  if (resolved.anyOf) {
    const nonNull = resolved.anyOf.find((branch) => branch.type !== "null");
    if (nonNull) resolved = { ...resolved, ...nonNull };
  }
  const ref = resolved.$ref ?? resolved.allOf?.[0]?.$ref;
  if (!ref) return resolved;
  const definition = schema.$defs?.[ref.split("/").pop() ?? ""] ?? {};
  return { ...definition, ...resolved };
}

/** Human form of a property's type: "enum(a | b)", "number ≥ 0 ≤ 1", "string"… */
export function typeLabel(prop: JsonSchemaProperty): string {
  if (prop.enum) return prop.enum.join(" | ");
  let label = prop.type ?? "any";
  if (prop.minimum !== undefined) label += ` ≥ ${prop.minimum}`;
  if (prop.exclusiveMinimum !== undefined) label += ` > ${prop.exclusiveMinimum}`;
  if (prop.maximum !== undefined) label += ` ≤ ${prop.maximum}`;
  if (prop.exclusiveMaximum !== undefined) label += ` < ${prop.exclusiveMaximum}`;
  return label;
}


const inputStyle: React.CSSProperties = {
  background: theme.color.surface2,
  color: theme.color.text,
  border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.m,
  padding: `${theme.space.xs + 2}px ${theme.space.s}px`,
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
  // A `X | None` property (see `deref`) can always be explicitly cleared back to "unset".
  const nullable = Boolean(prop.anyOf?.some((branch) => branch.type === "null"));

  let control: JSX.Element;
  if (resolved.enum) {
    control = (
      <select
        style={inputStyle}
        value={current === null || current === undefined ? "" : String(current)}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
      >
        {(nullable || current === null || current === undefined) && <option value="">—</option>}
        {resolved.enum.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    );
  } else if (resolved.type === "boolean") {
    control = <Switch checked={Boolean(current)} onChange={onChange} />;
  } else if (resolved.type === "number" || resolved.type === "integer") {
    control = (
      <NumberField
        value={typeof current === "number" ? current : undefined}
        min={resolved.minimum ?? resolved.exclusiveMinimum}
        max={resolved.maximum ?? resolved.exclusiveMaximum}
        style={inputStyle}
        onChange={onChange}
      />
    );
  } else if (resolved.type === "array" && resolved.items?.type === "string" && !resolved.items.enum) {
    // A flat string list gets the reusable tag editor instead of raw JSON — same control the
    // metadata schema step already uses for enum values / keyword_list.
    control = (
      <TagsInput
        values={Array.isArray(current) ? (current as string[]) : []}
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
        style={{ ...inputStyle, resize: "vertical", minHeight: theme.space.xl + 6, fontFamily: "inherit" }}
        value={text}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.size.s }}>
      {/* 1. Name + full type contract (+ required marker) */}
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs + 2, color: theme.color.dim }}>
        <span style={{ color: theme.color.text }}>
          {name}
          {required && <span style={{ color: theme.color.error }} title="required"> *</span>}
        </span>
        <span
          title={typeLabel(resolved)}
          style={{
            color: theme.color.mute, background: "transparent",
            border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.s, padding: `0 ${theme.space.xs + 1}px`, fontSize: theme.font.size.xs,
            fontFamily: theme.font.mono, whiteSpace: "nowrap", overflow: "hidden",
            // Fixed truncation column for the type badge — a layout constant, not a spacing
            // increment, so it stays a plain literal (matches the app's raw maxWidth convention
            // for component/container sizing, e.g. SearchStageFrame's icon offset).
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
