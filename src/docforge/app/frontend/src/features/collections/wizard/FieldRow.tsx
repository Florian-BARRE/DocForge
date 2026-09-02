// ====== Code Summary ======
// One editable schema row inside the wizard's step 2 table — every control reads its option
// list from the api layer's canonical enums, never an inline literal. Each cell's column header
// already names the control visually (the table's own <th>s), so a duplicate VISIBLE label per
// cell would be pure noise — instead every control gets a screen-reader-only <label htmlFor> tied
// to a per-row id (name/type/enum) so assistive tech still announces "Required, row: field name"
// rather than a bare, context-free control. Zero visual change.

import { FIELD_ORIGINS, FIELD_SCOPES, FIELD_TYPES } from "../../../api/collections";
import { humanizeEnumOption } from "../../../components/schema-form/fieldLabels";
import { Switch } from "../../../components/Switch";
import { TagsInput } from "../../../components/TagsInput";
import { inputStyle } from "../../../components/inputStyle";
import { theme } from "../../../theme";
import type { DraftField } from "./wizardTypes";

interface FieldRowProps {
  field: DraftField;
  onChange: (field: DraftField) => void;
  onRemove: () => void;
}

const cellStyle: React.CSSProperties = { padding: `${theme.space.m}px ${theme.space.s}px`, verticalAlign: "top" };

// Visually hidden but still in the a11y tree and focus/label-association order — the exact pattern
// already used by `FileInputButton`'s native-input stand-in, reused here for per-cell labels.
const srOnlyStyle: React.CSSProperties = {
  position: "absolute", width: 1, height: 1, padding: 0, margin: -1,
  overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap", border: 0,
};

/** Enum-value restriction only makes sense for a single string or a keyword-tag list. */
function supportsEnum(field: DraftField): boolean {
  return ["string", "keyword_list", "enum"].includes(field.field_type);
}

const FLAG_LABELS: Record<"required" | "filterable" | "lexical" | "semantic", string> = {
  required: "Required", filterable: "Filterable", lexical: "Lexical", semantic: "Semantic",
};

export function FieldRow({ field, onChange, onRemove }: FieldRowProps) {
  const set = <K extends keyof DraftField>(key: K, value: DraftField[K]) =>
    onChange({ ...field, [key]: value });

  // Stable per-row id root for htmlFor/id pairing — `_key` is already the row's own React key
  // (client-only, never submitted), so it's a safe DOM id source too.
  const rowId = field._key;
  const rowContext = field.field_name.trim() || "new field";

  return (
    <tr style={{ borderBottom: `1px solid ${theme.color.line}` }}>
      <td style={cellStyle}>
        <label htmlFor={`${rowId}-name`} style={srOnlyStyle}>Field name</label>
        <input
          id={`${rowId}-name`}
          style={{ ...inputStyle, fontFamily: theme.font.mono }}
          value={field.field_name}
          onChange={(e) => set("field_name", e.target.value)}
          placeholder="field_name"
          aria-required="true"
        />
      </td>
      <td style={cellStyle}>
        <label htmlFor={`${rowId}-type`} style={srOnlyStyle}>Type for {rowContext}</label>
        <select
          id={`${rowId}-type`}
          style={{ ...inputStyle, minWidth: 108 }}
          value={field.field_type}
          onChange={(e) => set("field_type", e.target.value as DraftField["field_type"])}
        >
          {FIELD_TYPES.map((t) => <option key={t} value={t}>{humanizeEnumOption(t)}</option>)}
        </select>
      </td>
      {(["required", "filterable", "lexical", "semantic"] as const).map((flag) => (
        <td key={flag} style={{ ...cellStyle, textAlign: "center" }}>
          <Switch checked={field[flag]} onChange={(checked) => set(flag, checked)} title={`${FLAG_LABELS[flag]} — ${rowContext}`} />
        </td>
      ))}
      <td style={{ ...cellStyle, minWidth: 180 }}>
        {supportsEnum(field) ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <TagsInput
              values={field.enum_values ?? []}
              onChange={(values) => set("enum_values", values.length ? values : null)}
              placeholder="type a value, press Enter"
              ariaLabel={`Enum values for ${rowContext}`}
            />
            <span style={{ color: field.field_type === "enum" && !(field.enum_values?.length)
                ? theme.color.error : theme.color.dim, fontSize: theme.font.size.xs }}>
              {field.field_type === "enum"
                ? "required — the ONLY values this field accepts"
                : "optional whitelist — restricts accepted values"}
            </span>
          </div>
        ) : (
          <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>n/a</span>
        )}
      </td>
      <td style={cellStyle}>
        <label htmlFor={`${rowId}-origin`} style={srOnlyStyle}>Origin for {rowContext}</label>
        <select
          id={`${rowId}-origin`}
          style={{ ...inputStyle, minWidth: 112 }}
          value={field.origin}
          onChange={(e) => {
            const origin = e.target.value as DraftField["origin"];
            set("origin", origin);
            if (origin !== "generated" && field.scope === "chunk") set("scope", "document");
          }}
        >
          {FIELD_ORIGINS.map((o) => <option key={o} value={o}>{humanizeEnumOption(o)}</option>)}
        </select>
      </td>
      <td style={cellStyle}>
        {/* Chunk scope is reserved for generated fields (backend + DB enforce it). minWidth is wide
            enough for the longest option label ("Document") plus the select's own affordance —
            narrower widths clip it to "Docume…". */}
        <label htmlFor={`${rowId}-scope`} style={srOnlyStyle}>Scope for {rowContext}</label>
        <select id={`${rowId}-scope`} style={{ ...inputStyle, minWidth: 132 }} value={field.scope} onChange={(e) => set("scope", e.target.value as DraftField["scope"])}>
          {FIELD_SCOPES.filter((s) => s !== "chunk" || field.origin === "generated").map((s) => (
            <option key={s} value={s}>{humanizeEnumOption(s)}</option>
          ))}
        </select>
      </td>
      <td style={{ ...cellStyle, textAlign: "center" }}>
        <span
          onClick={onRemove}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRemove(); } }}
          aria-label={`Remove ${rowContext}`}
          title="Remove field"
          style={{ cursor: "pointer", color: theme.color.dim, fontSize: theme.font.size.l }}
          onMouseEnter={(e) => (e.currentTarget.style.color = theme.color.error)}
          onMouseLeave={(e) => (e.currentTarget.style.color = theme.color.dim)}
        >
          ✕
        </span>
      </td>
    </tr>
  );
}
