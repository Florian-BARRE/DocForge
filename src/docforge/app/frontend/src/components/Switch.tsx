// ====== Code Summary ======
// A theme-tokened on/off switch — the reversible enable/disable control shared by documents and
// chunks in the explorer (and any future toggle). A styled button, not a native checkbox/switch.
//
// ON reads steel (theme.color.dim), NOT forge orange. Per brand.md, forge marks the ONE thing being
// worked (a running job, the active tab, a primary action) — a switch's "on" state is a static,
// simultaneously-true-for-many-rows fact (many toggles are on at once across a form/list), so it is
// decoration, not the active-one signal (2026-09 orange audit: this exact "on"=forge convention was
// the audit's #1 finding, cascading into every stage-enable and per-config boolean). A switch that
// can never be turned off (a required/locked stage) shares the same steel fill but adds a padlock
// glyph in the knob, so "can't turn this off" still reads as a distinct fact from "this happens to
// be on".

import { theme } from "../theme";

interface SwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  /** Required/locked control — always steel + a padlock glyph, never forge, and never interactive
   *  (implies disabled). Use for a stage/toggle that can never be turned off, not for a merely
   *  temporarily-disabled one — pair with `title` to explain why. */
  locked?: boolean;
  title?: string;
  /** Wires this switch (a labelable `<button>`) to an external `<label htmlFor>`. */
  id?: string;
}

const WIDTH = 34;
const HEIGHT = 18;
const KNOB = 14;
const EASE = "cubic-bezier(0.34, 1.56, 0.64, 1)"; // slight overshoot — the toggle feels tactile

function LockGlyph({ color }: { color: string }) {
  // Minimal padlock, sized to sit centered inside the knob.
  return (
    <svg width={8} height={8} viewBox="0 0 8 8" fill="none" style={{ display: "block" }}>
      <rect x="1" y="3.5" width="6" height="4" rx="1" stroke={color} strokeWidth="1" />
      <path d="M2.25 3.5V2.5a1.75 1.75 0 0 1 3.5 0v1" stroke={color} strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

export function Switch({ checked, onChange, disabled, locked, title, id }: SwitchProps) {
  const isLocked = Boolean(locked);
  const isInteractive = !disabled && !isLocked;
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      title={title}
      disabled={!isInteractive}
      onClick={() => onChange(!checked)}
      style={{
        width: WIDTH, height: HEIGHT, borderRadius: HEIGHT / 2,
        border: "none", padding: 2, position: "relative", flexShrink: 0,
        background: checked || isLocked ? theme.color.dim : theme.color.lineStrong,
        cursor: isInteractive ? "pointer" : "not-allowed",
        opacity: disabled && !isLocked ? 0.6 : 1,
        transition: `background .2s ease`,
      }}
    >
      <span
        style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          width: KNOB, height: KNOB, borderRadius: "50%",
          background: theme.color.onAccent, boxShadow: "0 1px 2px rgba(0,0,0,0.22)",
          transform: `translateX(${checked || isLocked ? WIDTH - KNOB - 4 : 0}px)`,
          transition: `transform .22s ${EASE}`,
        }}
      >
        {isLocked && <LockGlyph color={theme.color.dim} />}
      </span>
    </button>
  );
}
