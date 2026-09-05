// ====== Code Summary ======
// One JSON-Schema property rendered as the right control — enum → select, boolean → switch,
// number → numeric input, string → text (masked when the name smells like a secret) — with its
// full contract made visible: type (+ bounds / enum values), required flag, default, description.

import { useId, useState } from "react";
import type { JsonSchema, JsonSchemaProperty } from "../../api/types";
import { Switch } from "../Switch";
import { TagsInput } from "../TagsInput";
import { theme } from "../../theme";

import { humanizeEnumOption, humanizeFieldHelp, humanizeFieldLabel, humanizeFieldUnit, isSecretFieldName } from "./fieldLabels";
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

// Words in a description that signal the field is meant to hold multi-line prose (a prompt or
// template) even while its current/default value happens to be short or empty.
const MULTILINE_HINT_RE = /\b(prompt|template|multi-?line)\b/i;

/**
 * A frontend-only display heuristic (no schema-form contract change): a string field renders as a
 * single-line `<input>` unless its value/default already contains a newline, or its description
 * hints it's meant to hold prose (a prompt/template) — those keep the resizable `<textarea>`.
 */
export function isSingleLineString(text: string, description?: string): boolean {
  if (text.includes("\n")) return false;
  if (description && MULTILINE_HINT_RE.test(description)) return false;
  return true;
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
  // lineStrong, not line — see components/inputStyle.ts (this is SchemaField's own local copy).
  border: `1px solid ${theme.color.lineStrong}`,
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
  /** Progressive disclosure — when false (the default), the raw type/constraint badge and the
   *  `default: …` suffix are hidden so the form reads like a normal form, not a schema dump. Flip
   *  via the form's own "Show technical details" toggle. */
  advanced?: boolean;
}

export function SchemaField({ name, prop, schema, value, required = false, onChange, advanced = false }: SchemaFieldProps) {
  // Hooks first, before any control-shape branching below — a stable id to pair the visible
  // <label> with whichever control this property resolves to, and the reveal toggle for a
  // secret-looking field (unused, harmlessly, by every other control shape).
  const controlId = useId();
  const [revealed, setRevealed] = useState(false);

  const resolved = deref(prop, schema);
  const current = value === undefined ? resolved.default : value;
  // A `X | None` property (see `deref`) can always be explicitly cleared back to "unset".
  const nullable = Boolean(prop.anyOf?.some((branch) => branch.type === "null"));
  const ariaRequired = required || undefined;

  let control: JSX.Element;
  if (resolved.enum) {
    control = (
      <select
        id={controlId}
        aria-required={ariaRequired}
        style={inputStyle}
        value={current === null || current === undefined ? "" : String(current)}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
      >
        {(nullable || current === null || current === undefined) && <option value="">—</option>}
        {resolved.enum.map((option) => (
          <option key={option} value={option}>{humanizeEnumOption(option)}</option>
        ))}
      </select>
    );
  } else if (resolved.type === "boolean") {
    control = <Switch id={controlId} checked={Boolean(current)} onChange={onChange} />;
  } else if (resolved.type === "number" || resolved.type === "integer") {
    control = (
      <NumberField
        id={controlId}
        value={typeof current === "number" ? current : undefined}
        min={resolved.minimum ?? resolved.exclusiveMinimum}
        max={resolved.maximum ?? resolved.exclusiveMaximum}
        style={inputStyle}
        suffix={humanizeFieldUnit(name)}
        onChange={onChange}
      />
    );
  } else if (resolved.type === "array" && resolved.items?.type === "string" && !resolved.items.enum) {
    // A flat string list gets the reusable tag editor instead of raw JSON — same control the
    // metadata schema step already uses for enum values / keyword_list.
    control = (
      <TagsInput
        id={controlId}
        values={Array.isArray(current) ? (current as string[]) : []}
        onChange={onChange}
      />
    );
  } else if (resolved.type === "array" || resolved.type === "object") {
    // Structured values get a real JSON editor — committed only when the JSON parses,
    // so an array field can never receive a raw string.
    control = (
      <JsonField
        id={controlId}
        value={current ?? (resolved.type === "array" ? [] : {})}
        onChange={onChange}
      />
    );
  } else {
    // A plain single-line input for ordinary short strings (names, endpoints) — masked as a
    // password field when the name smells like a credential (api_key, token, …), with a show/hide
    // toggle since a masked field with a typo is otherwise unrecoverable; a resizable textarea only
    // for values that are actually multi-line or read as prose (prompts/templates) — see
    // `isSingleLineString`.
    const text = String(current ?? "");
    const secret = isSecretFieldName(name);
    control = isSingleLineString(text, resolved.description) ? (
      secret ? (
        <div style={{ display: "flex", gap: theme.space.xs }}>
          <input
            id={controlId}
            aria-required={ariaRequired}
            type={revealed ? "text" : "password"}
            autoComplete="off"
            style={{ ...inputStyle, flex: 1 }}
            value={text}
            onChange={(e) => onChange(e.target.value)}
          />
          <button
            type="button"
            onClick={() => setRevealed((prev) => !prev)}
            aria-label={revealed ? "Hide value" : "Show value"}
            style={{
              flex: "none",
              background: "none",
              border: `1px solid ${theme.color.lineStrong}`,
              borderRadius: theme.radius.m,
              color: theme.color.dim,
              fontSize: theme.font.size.xs,
              padding: `0 ${theme.space.s}px`,
              cursor: "pointer",
            }}
          >
            {revealed ? "Hide" : "Show"}
          </button>
        </div>
      ) : (
        <input
          id={controlId}
          aria-required={ariaRequired}
          type="text"
          style={inputStyle}
          value={text}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    ) : (
      <textarea
        id={controlId}
        aria-required={ariaRequired}
        rows={Math.min(6, Math.max(1, text.split("\n").length))}
        style={{ ...inputStyle, resize: "vertical", minHeight: theme.space.xl + 6, fontFamily: "inherit" }}
        value={text}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  const label = humanizeFieldLabel(name);
  const help = humanizeFieldHelp(name, resolved.description);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.size.s }}>
      {/* 1. Human label (+ required marker) — a real <label htmlFor> (not a detached <span>) so
         assistive tech announces it and clicking it focuses the paired control. The raw
         type/constraint contract only shows up in "Show technical details" mode, see SchemaForm's
         advanced toggle. */}
      <label htmlFor={controlId} style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs + 2, color: theme.color.dim }}>
        <span style={{ color: theme.color.text }}>
          {label}
          {required && <span style={{ color: theme.color.error }} title="required"> *</span>}
        </span>
        {advanced && (
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
        )}
      </label>
      {/* 2. The control itself */}
      {control}
      {/* 3. Meaning, always visible (not a hover-only tooltip) — the raw `default: …` suffix only
         shows in advanced mode: an unset default so often reads as noise ("default: null") to a
         normal user rather than useful information. */}
      {(help || (advanced && resolved.default !== undefined)) && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, lineHeight: 1.35 }}>
          {help}
          {advanced && resolved.default !== undefined && (
            <span style={{ color: theme.color.dim, opacity: 0.8 }}>
              {help ? " — " : ""}default: {String(resolved.default)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
