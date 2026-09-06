// ====== Code Summary ======
// Two DateInput fields (from/to) for a datetime-range column filter — created_at, or a datetime
// metadata field. Day-granularity (not a full datetime picker) is enough for corpus triage.
// Stacked (from above to) instead of side-by-side: a date field's own rendered value
// ("yyyy-mm-dd") needs more width than a narrow grid column has to spare two of side by side
// without truncating.

import { DateInput } from "../../../components/DateInput";

interface DateRangeInputsProps {
  gte: string;
  lte: string;
  onChange: (next: { gte: string; lte: string }) => void;
  /** The column's header text, used to build each bound's accessible name. */
  label?: string;
}

export function DateRangeInputs({ gte, lte, onChange, label }: DateRangeInputsProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <DateInput
        className="df-filter-input"
        value={gte}
        ariaLabel={label ? `${label} from` : "from"}
        onChange={(next) => onChange({ gte: next, lte })}
        style={{ width: "100%" }}
      />
      <DateInput
        className="df-filter-input"
        value={lte}
        ariaLabel={label ? `${label} to` : "to"}
        onChange={(next) => onChange({ gte, lte: next })}
        style={{ width: "100%" }}
      />
    </div>
  );
}
