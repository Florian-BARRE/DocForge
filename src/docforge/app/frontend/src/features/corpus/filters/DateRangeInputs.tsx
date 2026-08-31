// ====== Code Summary ======
// Two date inputs (from/to) for a datetime-range column filter — created_at, or a datetime
// metadata field. Kept as plain `<input type="date">` (a day-granularity bound is enough for
// corpus triage) rather than a full datetime picker.

import { theme } from "../../../theme";

interface DateRangeInputsProps {
  gte: string;
  lte: string;
  onChange: (next: { gte: string; lte: string }) => void;
}

const cellInputStyle: React.CSSProperties = {
  background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
  padding: "5px 6px", fontSize: 11, color: theme.color.text, width: "100%", fontFamily: theme.font.mono,
};

export function DateRangeInputs({ gte, lte, onChange }: DateRangeInputsProps) {
  return (
    <div style={{ display: "flex", gap: 4 }}>
      <input
        type="date"
        value={gte}
        onChange={(e) => onChange({ gte: e.target.value, lte })}
        style={cellInputStyle}
      />
      <input
        type="date"
        value={lte}
        onChange={(e) => onChange({ gte, lte: e.target.value })}
        style={cellInputStyle}
      />
    </div>
  );
}
