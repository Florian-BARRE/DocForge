// ====== Code Summary ======
// Two narrow number inputs (min/max) for a numeric-range column filter — file_size, page_count,
// or an integer/float metadata field.

import { theme } from "../../../theme";

interface NumberRangeInputsProps {
  gte: string;
  lte: string;
  onChange: (next: { gte: string; lte: string }) => void;
  /** The column's header text, used to build each bound's accessible name. */
  label?: string;
}

const cellInputStyle: React.CSSProperties = {
  background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
  padding: "5px 6px", fontSize: 12, color: theme.color.text, width: "100%", fontFamily: theme.font.mono,
};

export function NumberRangeInputs({ gte, lte, onChange, label }: NumberRangeInputsProps) {
  return (
    <div style={{ display: "flex", gap: 4 }}>
      <input
        type="number"
        value={gte}
        placeholder="min"
        aria-label={label ? `${label} minimum` : "minimum"}
        onChange={(e) => onChange({ gte: e.target.value, lte })}
        style={cellInputStyle}
      />
      <input
        type="number"
        value={lte}
        placeholder="max"
        aria-label={label ? `${label} maximum` : "maximum"}
        onChange={(e) => onChange({ gte, lte: e.target.value })}
        style={cellInputStyle}
      />
    </div>
  );
}
