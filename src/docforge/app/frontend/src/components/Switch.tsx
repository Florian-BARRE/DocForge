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

const WIDTH = 34;
const HEIGHT = 18;
const KNOB = 14;
const EASE = "cubic-bezier(0.34, 1.56, 0.64, 1)"; // slight overshoot — the toggle feels tactile

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
        background: checked ? theme.color.accent : theme.color.lineStrong,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        transition: `background .2s ease`,
      }}
    >
      <span
        style={{
          display: "block", width: KNOB, height: KNOB, borderRadius: "50%",
          background: theme.color.onAccent, boxShadow: "0 1px 2px rgba(0,0,0,0.22)",
          transform: `translateX(${checked ? WIDTH - KNOB - 4 : 0}px)`,
          transition: `transform .22s ${EASE}`,
        }}
      />
    </button>
  );
}
