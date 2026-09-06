// ====== Code Summary ======
// A single big-number tile — the shared card for the "one figure that's the point" pattern (fleet
// counts on Home/Monitoring). Per brand.md, big-number treatment is reserved for figures that ARE
// the point; everything else on a dashboard stays quiet body text. Optionally clickable (renders as
// a keyboard-operable `role="button"` div rather than a native `<button>`, so its internal layout
// stays free of browser button resets).

import type { KeyboardEvent, ReactNode } from "react";
import { theme } from "../theme";

export type StatTileTone = "accent" | "warn" | "error" | "ok" | "neutral";

const TONE_COLOR: Record<StatTileTone, string> = {
  accent: theme.color.accentSafe,
  warn: theme.color.warn,
  error: theme.color.error,
  ok: theme.color.ok,
  neutral: theme.color.text,
};

interface StatTileProps {
  value: ReactNode;
  label: string;
  tone?: StatTileTone;
  /** A short line under the label — extra context (e.g. "3 offline"). */
  caption?: ReactNode;
  onClick?: () => void;
  title?: string;
}

export function StatTile({ value, label, tone = "neutral", caption, onClick, title }: StatTileProps) {
  const onKeyDown = (e: KeyboardEvent) => {
    if (!onClick) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onKeyDown}
      title={title}
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.xs, textAlign: "left", minWidth: 150,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
        boxShadow: theme.shadow.sm, padding: `${theme.space.m}px ${theme.space.l}px`,
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.display, fontWeight: theme.font.weight.semibold, color: TONE_COLOR[tone] }}>
        {value}
      </span>
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>{label}</span>
      {caption && <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>{caption}</span>}
    </div>
  );
}
