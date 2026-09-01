// ====== Code Summary ======
// Two date inputs (from/to) for a datetime-range column filter — created_at, or a datetime
// metadata field. Kept as plain `<input type="date">` (a day-granularity bound is enough for
// corpus triage) rather than a full datetime picker.

import { inputStyle } from "../../../components/inputStyle";
import { useTheme } from "../../../shell/useTheme";
import { theme } from "../../../theme";

interface DateRangeInputsProps {
  gte: string;
  lte: string;
  onChange: (next: { gte: string; lte: string }) => void;
}

export function DateRangeInputs({ gte, lte, onChange }: DateRangeInputsProps) {
  // Native date-picker/spinner chrome tracks `color-scheme`, not our CSS variables — without this
  // it always renders light, looking foreign against the ink theme.
  const { theme: activeTheme } = useTheme();
  const cellInputStyle: React.CSSProperties = {
    ...inputStyle, borderRadius: theme.radius.s, padding: "5px 6px",
    fontSize: 11, fontFamily: theme.font.mono, colorScheme: activeTheme,
  };

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
