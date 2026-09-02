// ====== Code Summary ======
// The on/off switch every stage card uses to enable/disable itself — a plain checkbox styled as
// a pill, disabled (with a tooltip explaining why) for stages that can never be turned off. ON
// reads in steel: several stages are enabled at once, and forge orange is reserved for the one
// thing actively being worked, not a static at-rest state — see brand.md.

import { theme } from "../../theme";

interface StageSwitchProps {
  checked: boolean;
  disabled?: boolean;
  title?: string;
  onChange: (checked: boolean) => void;
}

export function StageSwitch({ checked, disabled = false, title, onChange }: StageSwitchProps) {
  return (
    <label
      title={title}
      style={{
        display: "inline-flex", alignItems: "center", flexShrink: 0,
        cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.45 : 1,
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
      />
      <span
        style={{
          position: "relative", width: 34, height: 18, borderRadius: theme.radius.pill,
          background: checked ? theme.color.accent : theme.color.line,
          transition: "background .15s ease",
        }}
      >
        <span
          style={{
            position: "absolute", top: 2, left: checked ? 18 : 2, width: 14, height: 14,
            borderRadius: "50%", background: theme.color.onAccent, transition: "left .15s ease",
            boxShadow: theme.shadow.sm,
          }}
        />
      </span>
    </label>
  );
}
