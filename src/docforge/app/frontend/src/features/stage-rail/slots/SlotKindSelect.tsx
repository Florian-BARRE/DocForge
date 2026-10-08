// ====== Code Summary ======
// The provider-kind select of one slot. A kind the slot can in principle take but this deployment
// cannot serve (absent from `deployed`) stays visible yet disabled, so the user sees WHY it is not
// pickable instead of the option silently vanishing.

import { inputStyle } from "../../../components/inputStyle";
import { theme } from "../../../theme";

interface SlotKindSelectProps {
  label: string;
  value: string | null;
  available: string[];
  /** Kinds this deployment can serve; `null` = unknown, nothing is greyed. */
  deployed: string[] | null;
  onSelect: (kind: string) => void;
}

export function SlotKindSelect({ label, value, available, deployed, onSelect }: SlotKindSelectProps) {
  return (
    <select
      aria-label={label}
      value={value ?? ""}
      onChange={(e) => e.target.value && onSelect(e.target.value)}
      style={{
        ...inputStyle, width: "auto", minWidth: 200, fontFamily: theme.font.mono, fontWeight: 600,
        borderRadius: theme.radius.m,
      }}
    >
      {value === null && <option value="" disabled>Off — choose a provider…</option>}
      {available.map((kind) => {
        const unavailable = deployed !== null && !deployed.includes(kind);
        return (
          <option key={kind} value={kind} disabled={unavailable} style={unavailable ? { color: theme.color.dim } : undefined}>
            {unavailable ? `${kind} (unavailable here)` : kind}
          </option>
        );
      })}
    </select>
  );
}
