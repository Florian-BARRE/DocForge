// ====== Code Summary ======
// One editable schema row inside the wizard's step 2 table — every control reads its option
// list from the api layer's canonical enums, never an inline literal.

import { FIELD_ORIGINS, FIELD_SCOPES, FIELD_TYPES } from "../../../api/collections";
import { TagsInput } from "../../../components/TagsInput";
import { inputStyle } from "../../../components/inputStyle";
import { theme } from "../../../theme";
import type { DraftField } from "./wizardTypes";

interface FieldRowProps {
  field: DraftField;
  onChange: (field: DraftField) => void;
  onRemove: () => void;
}

const cellStyle: React.CSSProperties = { padding: `${theme.space.xs}px ${theme.space.s}px`, verticalAlign: "top" };
const checkboxStyle: React.CSSProperties = { width: 15, height: 15, accentColor: theme.color.accent };

/** Enum-value restriction only makes sense for a single string or a keyword-tag list. */
function supportsEnum(field: DraftField): boolean {
  return ["string", "keyword_list", "enum"].includes(field.field_type);
}

export function FieldRow({ field, onChange, onRemove }: FieldRowProps) {
  const set = <K extends keyof DraftField>(key: K, value: DraftField[K]) =>
    onChange({ ...field, [key]: value });

  return (
    <tr style={{ borderBottom: `1px solid ${theme.color.line}` }}>
      <td style={cellStyle}>
        <input
          style={inputStyle}
          value={field.field_name}
          onChange={(e) => set("field_name", e.target.value)}
          placeholder="field_name"
        />
      </td>
      <td style={cellStyle}>
        <select
          style={inputStyle}
          value={field.field_type}
          onChange={(e) => set("field_type", e.target.value as DraftField["field_type"])}
        >
          {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </td>
      {(["required", "filterable", "lexical", "semantic"] as const).map((flag) => (
        <td key={flag} style={{ ...cellStyle, textAlign: "center" }}>
          <input
            type="checkbox"
            style={checkboxStyle}
            checked={field[flag]}
            onChange={(e) => set(flag, e.target.checked)}
          />
        </td>
      ))}
      <td style={{ ...cellStyle, minWidth: 160 }}>
        {supportsEnum(field) ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <TagsInput
              values={field.enum_values ?? []}
              onChange={(values) => set("enum_values", values.length ? values : null)}
              placeholder="type a value, press Enter"
            />
            <span style={{ color: field.field_type === "enum" && !(field.enum_values?.length)
                ? theme.color.error : theme.color.dim, fontSize: theme.font.size.xs }}>
              {field.field_type === "enum"
                ? "required — the ONLY values this field accepts"
                : "optional whitelist — restricts accepted values"}
            </span>
          </div>
        ) : (
          <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>n/a</span>
        )}
      </td>
      <td style={cellStyle}>
        <select
          style={inputStyle}
          value={field.origin}
          onChange={(e) => {
            const origin = e.target.value as DraftField["origin"];
            set("origin", origin);
            if (origin !== "generated" && field.scope === "chunk") set("scope", "document");
          }}
        >
          {FIELD_ORIGINS.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </td>
      <td style={cellStyle}>
        {/* Chunk scope is reserved for generated fields (backend + DB enforce it). */}
        <select style={inputStyle} value={field.scope} onChange={(e) => set("scope", e.target.value as DraftField["scope"])}>
          {FIELD_SCOPES.filter((s) => s !== "chunk" || field.origin === "generated").map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </td>
      <td style={cellStyle}>
        <span
          onClick={onRemove}
          title="Remove field"
          style={{ cursor: "pointer", color: theme.color.error, fontSize: theme.font.size.m }}
        >
          ✕
        </span>
      </td>
    </tr>
  );
}
