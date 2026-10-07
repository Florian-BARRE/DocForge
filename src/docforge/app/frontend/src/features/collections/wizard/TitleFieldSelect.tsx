// ====== Code Summary ======
// "Title field" selector — picks which document-scope metadata field supplies each document's
// display title. Options are derived from the draft schema (never a hardcoded list), so a field
// added or renamed in the table above is immediately selectable. The empty option maps to `null`
// (explicit clear -> fall back to the parsed title).

import { inputStyle } from "../../../components/inputStyle";
import { theme } from "../../../theme";
import type { DraftField } from "./wizardTypes";
import { documentFieldNames } from "./wizardTypes";

interface TitleFieldSelectProps {
  fields: DraftField[];
  value: string | null;
  onChange: (value: string | null) => void;
  /** Backend 422 message about the title field (valid choices are listed in it), shown inline. */
  error?: string | null;
}

const NONE_VALUE = "";

export function TitleFieldSelect({ fields, value, onChange, error }: TitleFieldSelectProps) {
  const names = documentFieldNames(fields);
  // A stale selection (field renamed/removed in the draft) is shown as "None" — the payload
  // builder clears it too, matching the backend's auto-clear.
  const selected = value !== null && names.includes(value) ? value : NONE_VALUE;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, maxWidth: 420 }}>
      <label htmlFor="collection-title-field" style={{ fontSize: theme.font.size.m, fontWeight: theme.font.weight.semibold, color: theme.color.text }}>
        Title field
      </label>
      <select
        id="collection-title-field"
        style={inputStyle}
        value={selected}
        onChange={(e) => onChange(e.target.value === NONE_VALUE ? null : e.target.value)}
      >
        <option value={NONE_VALUE}>None (use the parsed title)</option>
        {names.map((name) => <option key={name} value={name}>{name}</option>)}
      </select>
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>
        The metadata field whose value is shown as each document's title.
      </span>
      {error && <span role="alert" style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</span>}
    </div>
  );
}
