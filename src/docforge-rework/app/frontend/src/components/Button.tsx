// ====== Code Summary ======
// The shared button — primary (accent fill), secondary (outline) and danger (error outline)
// variants, matching the rounded look already used throughout the pipeline studio.

import type { ButtonHTMLAttributes } from "react";
import { theme } from "../theme";

export type ButtonVariant = "primary" | "secondary" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const VARIANT_STYLE: Record<ButtonVariant, React.CSSProperties> = {
  primary: { background: theme.color.accent, color: "#fff", border: "none" },
  secondary: { background: "none", color: theme.color.accent, border: `1px solid ${theme.color.accent}` },
  danger: { background: "none", color: theme.color.error, border: `1px solid ${theme.color.error}` },
};

export function Button({ variant = "secondary", style, disabled, ...rest }: ButtonProps) {
  const base: React.CSSProperties = {
    borderRadius: theme.radius.s,
    padding: "5px 14px",
    fontSize: theme.font.size.m,
    cursor: disabled ? "not-allowed" : "pointer",
  };
  const variantStyle = disabled
    ? { background: theme.color.card, color: theme.color.dim, border: "none" }
    : VARIANT_STYLE[variant];
  return <button disabled={disabled} style={{ ...base, ...variantStyle, ...style }} {...rest} />;
}
