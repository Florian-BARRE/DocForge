// ====== Code Summary ======
// Central design tokens — every color, radius and spacing in the app comes from here.
// No component hardcodes a color value.

export const theme = {
  color: {
    bg: "#0f1115",
    panel: "#181b22",
    card: "#1f2430",
    cardHover: "#242a38",
    line: "#2c3342",
    text: "#d7dce5",
    dim: "#8b93a5",
    onAccent: "#fff",
    accent: "#4f8cff",
    accentSoft: "rgba(79,140,255,.14)",
    ok: "#3ecf8e",
    okSoft: "rgba(62,207,142,.14)",
    error: "#ff5c6c",
    errorSoft: "rgba(255,92,108,.14)",
    warn: "#f0b429",
    warnSoft: "rgba(240,180,41,.14)",
    loop: "#9a6cff",
    loopSoft: "rgba(154,108,255,.08)",
    edge: "#55607a",
    // Fallback chains (model-call escalation sites) get their OWN accent so they read as a
    // distinct concept from the linear stage rail wherever they appear (enrich's OCR/VLM sites).
    chain: "#22d3ee",
    chainSoft: "rgba(34,211,238,.10)",
  },
  radius: { s: 4, m: 8, l: 12 },
  space: { xs: 4, s: 8, m: 12, l: 16 },
  font: {
    family: "system-ui, -apple-system, 'Segoe UI', sans-serif",
    mono: "'Cascadia Code', Consolas, monospace",
    size: { xs: 10, s: 11, m: 12, l: 13, xl: 15 },
  },
} as const;

export type Theme = typeof theme;
