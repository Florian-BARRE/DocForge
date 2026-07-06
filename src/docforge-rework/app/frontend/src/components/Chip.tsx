// ====== Code Summary ======
// A small colored pill — the shared visual language for status/flag indicators across features
// (job status, needs-reindex, format tags). Tone maps to the matching theme color pair, mirroring
// the badge look already used by the pipeline studio's PaletteCard.

import type { ReactNode } from "react";
import { theme } from "../theme";

export type ChipTone = "accent" | "ok" | "warn" | "error" | "dim" | "loop";

const TONE_COLOR: Record<ChipTone, { color: string; background: string }> = {
  accent: { color: theme.color.accent, background: theme.color.accentSoft },
  ok: { color: theme.color.ok, background: theme.color.okSoft },
  warn: { color: theme.color.warn, background: theme.color.warnSoft },
  error: { color: theme.color.error, background: theme.color.errorSoft },
  dim: { color: theme.color.dim, background: theme.color.card },
  loop: { color: theme.color.loop, background: theme.color.loopSoft },
};

interface ChipProps {
  tone?: ChipTone;
  children: ReactNode;
  title?: string;
}

export function Chip({ tone = "dim", children, title }: ChipProps) {
  const { color, background } = TONE_COLOR[tone];
  return (
    <span
      title={title}
      style={{
        color, background, borderRadius: 10, padding: "1px 7px",
        fontSize: theme.font.size.xs, fontWeight: 700, whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}
