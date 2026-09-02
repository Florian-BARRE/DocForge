// ====== Code Summary ======
// A small pill — the shared visual language for status/flags/tags (job status, needs-reindex,
// format tags, field surfaces). Tone maps to a colour pair from the palette variables, so chips
// reskin per theme. `neutral` is the quiet surface pill used for plain tags.

import type { ReactNode } from "react";
import { theme as t } from "../theme";

export type ChipTone = "accent" | "ok" | "warn" | "error" | "info" | "neutral" | "dim" | "loop" | "skip" | "capability";

// Text always uses the tone's "-strong" step, never the base tone — the base tone is tuned to read
// well as a soft FILL/border, not as small text over its own tint (warn/skip/iris fall under 2.5:1
// as text at base value). `accent` uses `accentSafe` for the same reason (base accent fails ~3.4:1
// on paper). Fills/borders stay on the base tone.
const TONE: Record<ChipTone, { color: string; background: string; border: string; dashed?: boolean }> = {
  accent: { color: t.color.accentSafe, background: t.color.accentSoft, border: t.color.accentLine },
  ok: { color: t.color.okStrong, background: t.color.okSoft, border: "transparent" },
  warn: { color: t.color.warnStrong, background: t.color.warnSoft, border: "transparent" },
  error: { color: t.color.errorStrong, background: t.color.errorSoft, border: "transparent" },
  info: { color: t.color.infoStrong, background: t.color.infoSoft, border: "transparent" },
  loop: { color: t.color.loopStrong, background: t.color.loopSoft, border: "transparent" },
  // A passive capability/origin tag (user-authored field, semantic/lexical/filterable surface) —
  // steel, deliberately never forge or the "done" green. See theme.ts's `capability` token.
  capability: { color: t.color.capabilityStrong, background: t.color.capabilitySoft, border: "transparent" },
  neutral: { color: t.color.dim, background: t.color.surface2, border: t.color.line },
  // Quiet meta tag (family/kind/flags) — a hairline outline on no fill, so it reads as metadata
  // beside a title rather than a heavy grey slab.
  dim: { color: t.color.mute, background: "transparent", border: t.color.line },
  // A deliberate stop (cancelled job/document, skipped stage) — dashed per brand.md, never the
  // error red (it wasn't a failure).
  skip: { color: t.color.skipStrong, background: t.color.skipSoft, border: t.color.skip, dashed: true },
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
        color: c.color, background: c.background, border: `1px ${c.dashed ? "dashed" : "solid"} ${c.border}`,
        borderRadius: t.radius.pill, padding: "2px 9px",
        fontSize: t.font.size.xs, fontWeight: 600, letterSpacing: "0.01em", whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}
