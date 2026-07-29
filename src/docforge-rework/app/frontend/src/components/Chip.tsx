// ====== Code Summary ======
// A small pill — the shared visual language for status/flags/tags (job status, needs-reindex,
// format tags, field surfaces). Tone maps to a colour pair from the palette variables, so chips
// reskin per theme. `neutral` is the quiet surface pill used for plain tags.

import type { ReactNode } from "react";
import { theme as t } from "../theme";

export type ChipTone = "accent" | "ok" | "warn" | "error" | "info" | "neutral" | "dim" | "loop";

const TONE: Record<ChipTone, { color: string; background: string; border: string }> = {
  accent: { color: t.color.accent, background: t.color.accentSoft, border: t.color.accentLine },
  ok: { color: t.color.ok, background: t.color.okSoft, border: "transparent" },
  warn: { color: t.color.warn, background: t.color.warnSoft, border: "transparent" },
  error: { color: t.color.error, background: t.color.errorSoft, border: "transparent" },
  info: { color: t.color.info, background: t.color.infoSoft, border: "transparent" },
  loop: { color: t.color.loop, background: t.color.loopSoft, border: "transparent" },
  neutral: { color: t.color.dim, background: t.color.surface2, border: t.color.line },
  dim: { color: t.color.mute, background: t.color.surface2, border: "transparent" },
};

interface ChipProps {
  tone?: ChipTone;
  children: ReactNode;
  title?: string;
}

export function Chip({ tone = "neutral", children, title }: ChipProps) {
  const c = TONE[tone];
  return (
    <span
      title={title}
      style={{
        display: "inline-flex", alignItems: "center",
        color: c.color, background: c.background, border: `1px solid ${c.border}`,
        borderRadius: t.radius.pill, padding: "2px 9px",
        fontSize: t.font.size.xs, fontWeight: 600, letterSpacing: "0.01em", whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}
