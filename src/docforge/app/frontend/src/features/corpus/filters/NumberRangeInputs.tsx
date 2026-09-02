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

// A floor wide enough for the "min"/"max" placeholder to render in full at 12px mono — without it
// the flex row silently shrinks each input below its own text (browsers give a bare <input> no
// intrinsic min-width of its own), truncating to "m"/"mi".
const INPUT_MIN_WIDTH = 46;

const cellInputStyle: React.CSSProperties = {
  background: theme.color.surface2, border: `1px solid ${theme.color.lineStrong}`, borderRadius: theme.radius.s,
  padding: "5px 6px", fontSize: 12, color: theme.color.text, width: "100%", minWidth: INPUT_MIN_WIDTH,
  fontFamily: theme.font.mono,
};

export function NumberRangeInputs({ gte, lte, onChange, label }: NumberRangeInputsProps) {
  return (
    <div style={{ display: "flex", gap: 4 }}>
      <input
        type="number"
        className="df-filter-input"
        value={gte}
        placeholder="min"
        aria-label={label ? `${label} minimum` : "minimum"}
        onChange={(e) => onChange({ gte: e.target.value, lte })}
        style={cellInputStyle}
      />
      <input
        type="number"
        className="df-filter-input"
        value={lte}
        placeholder="max"
        aria-label={label ? `${label} maximum` : "maximum"}
        onChange={(e) => onChange({ gte, lte: e.target.value })}
        style={cellInputStyle}
      />
    </div>
  );
}
