// ====== Code Summary ======
// The shared button. Variants: primary (ember fill), secondary (tonal surface), ghost (quiet),
// danger (error tonal). Hover/press are handled with local state so the whole app gets a
// consistent, tactile feel from one place. Palette-variable colours → reskins per theme.

import { useState, type ButtonHTMLAttributes } from "react";
import { theme as t } from "../theme";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

function variantStyle(variant: ButtonVariant, hover: boolean): React.CSSProperties {
  switch (variant) {
    case "primary":
      // Rest fill is `accentSafe` (accent-strong on paper — plain `accent` fails ~3.4:1 under the
      // white knockout text; unchanged on ink, already ~6:1). Hover always steps to `accentStrong`,
      // which on ink is what "rest" used to be — so ink stays byte-identical to before this pass.
      return {
        background: hover ? t.color.accentStrong : t.color.accentSafe,
        color: t.color.onAccent, border: "1px solid transparent",
        boxShadow: hover ? `0 6px 18px -6px ${t.color.accent}` : t.shadow.sm,
      };
    case "ghost":
      return {
        background: hover ? t.color.surface2 : "transparent",
        color: t.color.text, border: "1px solid transparent",
      };
    case "danger":
      // Border is always `error` (not just on hover) — a danger action must read as one at rest,
      // not only once you're already hovering it.
      return {
        background: hover ? t.color.errorSoft : "transparent",
        color: t.color.error, border: `1px solid ${t.color.error}`,
      };
    default: // secondary — tonal
      return {
        background: hover ? t.color.surface3 : t.color.surface2,
        color: t.color.text, border: `1px solid ${t.color.line}`,
      };
  }
}

export function Button({ variant = "secondary", size = "md", style, disabled, ...rest }: ButtonProps) {
  const [hover, setHover] = useState(false);
  const [press, setPress] = useState(false);
  const base: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7,
    borderRadius: t.radius.m,
    padding: size === "sm" ? "5px 11px" : "8px 15px",
    fontSize: size === "sm" ? t.font.size.m : t.font.size.l,
    fontWeight: t.font.weight.semibold, lineHeight: 1.1,
    cursor: disabled ? "not-allowed" : "pointer",
    transition: "background .15s ease, box-shadow .15s ease, border-color .15s ease, transform .06s ease",
    transform: press && !disabled ? "translateY(1px)" : "none",
    whiteSpace: "nowrap",
  };
  const skin = disabled
    ? { background: t.color.surface2, color: t.color.mute, border: `1px solid ${t.color.line}`, boxShadow: "none" }
    : variantStyle(variant, hover);
  return (
    <button
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPress(false); }}
      onMouseDown={() => setPress(true)}
      onMouseUp={() => setPress(false)}
      style={{ ...base, ...skin, ...style }}
      {...rest}
    />
  );
}
