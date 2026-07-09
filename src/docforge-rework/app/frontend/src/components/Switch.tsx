// ====== Code Summary ======
// A theme-tokened on/off switch — the reversible enable/disable control shared by documents and
// chunks in the explorer (and any future toggle). A styled button, not a native checkbox/switch.

import { theme } from "../theme";

interface SwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  title?: string;
}

const WIDTH = 30;
const HEIGHT = 16;
const KNOB = 12;

export function Switch({ checked, onChange, disabled, title }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      title={title}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      style={{
        width: WIDTH, height: HEIGHT, borderRadius: HEIGHT / 2,
        border: "none", padding: 2, position: "relative", flexShrink: 0,
        background: checked ? theme.color.accent : theme.color.line,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        transition: "background .15s",
      }}
    >
      <span
        style={{
          display: "block", width: KNOB, height: KNOB, borderRadius: "50%",
          background: "#fff", transform: `translateX(${checked ? WIDTH - KNOB - 4 : 0}px)`,
          transition: "transform .15s",
        }}
      />
    </button>
  );
}
