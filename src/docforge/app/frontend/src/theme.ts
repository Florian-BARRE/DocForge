// ====== Code Summary ======
// Central design tokens. Colours resolve to CSS variables defined in index.css, so BOTH the light
// and dark palettes work with no component changes — flip via
// document.documentElement.dataset.theme. No component hardcodes a colour value.

export const theme = {
  color: {
    // Surfaces (low → high elevation).
    bg: "var(--bg)",
    panel: "var(--panel)",
    surface: "var(--surface)",
    surface2: "var(--surface-2)",
    surface3: "var(--surface-3)",
    card: "var(--surface)",        // legacy alias
    cardHover: "var(--surface-2)", // legacy alias

    // Lines.
    line: "var(--line)",
    lineStrong: "var(--line-strong)",
    edge: "var(--line-strong)", // graph-edge alias

    // Text.
    text: "var(--text)",
    dim: "var(--text-dim)",
    mute: "var(--text-mute)",

    // Accent (the ember/forge signature).
    accent: "var(--accent)",
    accentStrong: "var(--accent-strong)",
    accentSoft: "var(--accent-soft)",
    accentLine: "var(--accent-line)",
    onAccent: "var(--accent-contrast)",

    // Semantics.
    ok: "var(--ok)", okSoft: "var(--ok-soft)",
    error: "var(--error)", errorSoft: "var(--error-soft)",
    warn: "var(--warn)", warnSoft: "var(--warn-soft)",
    info: "var(--info)", infoSoft: "var(--info-soft)",
    // Fallback chains + loop concepts get their own hues so they read as distinct.
    loop: "var(--iris)", loopSoft: "var(--iris-soft)", // legacy alias
    iris: "var(--iris)", irisSoft: "var(--iris-soft)",
    chain: "var(--chain)", chainSoft: "var(--chain-soft)",
  },
  radius: { s: 6, m: 10, l: 14, xl: 20, pill: 999 },
  space: { xs: 4, s: 8, m: 12, l: 16, xl: 24, xxl: 40 },
  shadow: { sm: "var(--shadow-1)", md: "var(--shadow-2)", pop: "var(--shadow-pop)" },
  font: {
    // Archivo is the whole UI voice (labels, nav, headings, body). JetBrains Mono is reserved for
    // machine values only (ids, hashes, scores, timings, dims, versions) — never prose. See docs/brand.md.
    family: "'Archivo', system-ui, -apple-system, sans-serif",
    display: "'Archivo', system-ui, -apple-system, sans-serif",
    mono: "'JetBrains Mono', ui-monospace, 'Cascadia Code', Consolas, monospace",
    weight: { normal: 400, medium: 500, semibold: 600, bold: 700 },
    // Bumped from the cramped 10–15px scale to a properly breathing one.
    size: { xs: 11, s: 12, m: 13, l: 14, xl: 16, xxl: 20, display: 28 },
  },
} as const;

export type Theme = typeof theme;
