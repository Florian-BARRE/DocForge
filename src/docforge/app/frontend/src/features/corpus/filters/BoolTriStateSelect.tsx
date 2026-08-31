// ====== Code Summary ======
// A three-state select (Any / true / false) for boolean columns — `enabled` and any bool-typed
// metadata field.

import { inputStyle } from "../../../components/inputStyle";

interface BoolTriStateSelectProps {
  value: boolean | null;
  onChange: (value: boolean | null) => void;
  trueLabel?: string;
  falseLabel?: string;
}

export function BoolTriStateSelect({ value, onChange, trueLabel = "true", falseLabel = "false" }: BoolTriStateSelectProps) {
  return (
    <select
      value={value === null ? "" : String(value)}
      onChange={(e) => onChange(e.target.value === "" ? null : e.target.value === "true")}
      style={{ ...inputStyle, padding: "5px 6px", fontSize: 12 }}
    >
      <option value="">any</option>
      <option value="true">{trueLabel}</option>
      <option value="false">{falseLabel}</option>
    </select>
  );
}
