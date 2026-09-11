// ====== Code Summary ======
// A theme-tokened on/off switch — the reversible enable/disable control shared by documents and
// chunks in the explorer, schema-driven boolean fields, and any future toggle. A styled button, not
// a native checkbox/switch.
//
// ON reads forge orange (theme.color.accent), matching `StageSwitch` (the stage-rail's own
// enable/disable pill) byte-for-byte. The 2026-08 orange audit had moved this control's "on" state
// to steel, reasoning that a simultaneously-true-for-many-rows fact shouldn't wear the "one active
// thing" color — but the 2026-09 round-4 product audit (5-persona) measured the resulting split
// (stage toggles orange, every other boolean switch steel) as the #1 inconsistency: users read two
// different toggle languages for the same on/off gesture. Superseded: ONE toggle language, ON =
// accent, everywhere. A switch that can never be turned off (a required/locked stage) keeps the
// steel fill + padlock glyph in the knob — "can't turn this off" is a distinct fact from "this is
// currently on", so it deliberately does NOT share the accent.

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
        background: isLocked ? theme.color.dim : checked ? theme.color.accent : theme.color.line,
        cursor: isInteractive ? "pointer" : "not-allowed",
        opacity: disabled && !isLocked ? 0.6 : 1,
        transition: `background .2s ease`,
      }}
    >
      <span
        style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          width: KNOB, height: KNOB, borderRadius: "50%",
          background: theme.color.onAccent, boxShadow: `0 1px 2px ${theme.color.knobShadow}`,
          transform: `translateX(${checked || isLocked ? WIDTH - KNOB - 4 : 0}px)`,
          transition: `transform .22s ${EASE}`,
        }}
      >
        {isLocked && <LockGlyph color={theme.color.dim} />}
      </span>
    </button>
  );
}
