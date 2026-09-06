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
    // The AA-safe accent for the CURRENT theme — resolves to accent-strong on paper (base --accent
    // fails ~3.4:1 as text/fill under light knockout content) and to plain --accent on ink (already
    // ~6:1, unchanged). Use this — never raw `accent` — for any accent rendered as TEXT on a paper-ish
    // surface, or as a solid fill that carries light knockout text (see Button primary). Documented
    // for page-owning agents in agent-memory/frontend/design-round1-2026-09.md.
    accentSafe: "var(--accent-safe)",
    // One step darker than accentSafe — for accent TEXT on a tinted card surface (surface-2), where
    // accentSafe's paper-tuned ~4.35:1 falls under AA. Narrow use: SearchHitCard's "view page" link.
    accentStrongOnSurface: "var(--accent-strong-on-surface)",
    accentSoft: "var(--accent-soft)",
    accentLine: "var(--accent-line)",
    onAccent: "var(--accent-contrast)",

    // Semantics. Each has a "-strong" text-safe step for when the tone is rendered as TEXT over its
    // own soft tint (a chip) rather than as a plain icon/border — several base tones (warn, skip,
    // iris/chain) fail AA as text at their base value. Fills stay unchanged; only text should switch.
    ok: "var(--ok)", okSoft: "var(--ok-soft)", okStrong: "var(--ok-strong)",
    error: "var(--error)", errorSoft: "var(--error-soft)", errorStrong: "var(--error-strong)",
    warn: "var(--warn)", warnSoft: "var(--warn-soft)", warnStrong: "var(--warn-strong)",
    info: "var(--info)", infoSoft: "var(--info-soft)", infoStrong: "var(--info-strong)",
    // A stopped/skipped state — cancelled jobs+documents, skipped stages. Deliberately NOT the
    // error red (per brand.md, "cancelled" reads as a deliberate stop, not a failure).
    skip: "var(--skip)", skipSoft: "var(--skip-soft)", skipStrong: "var(--skip-strong)",
    // Fallback chains + loop concepts get their own hues so they read as distinct.
    loop: "var(--iris)", loopSoft: "var(--iris-soft)", loopStrong: "var(--iris-strong)", // legacy alias
    iris: "var(--iris)", irisSoft: "var(--iris-soft)", irisStrong: "var(--iris-strong)",
    chain: "var(--chain)", chainSoft: "var(--chain-soft)", chainStrong: "var(--chain-strong)",
    // A passive capability/origin flag (e.g. "user"-authored field, a metadata surface like
    // semantic/lexical/filterable) — steel, never a status colour. Reserved for badges that
    // describe WHAT something is, not whether it succeeded/failed/is-the-active-one; per
    // brand.md, forge and the "done" green are both off-limits for this kind of passive tag.
    capability: "var(--capability)", capabilitySoft: "var(--capability-soft)", capabilityStrong: "var(--capability-strong)",

    // Categorical data-viz triad — one hue per physical store on the storage-footprint panel.
    // Warm steel / muted gold-ochre / olive-moss: three distinct warm hues, never the forge accent
    // or the error/warn status inks (postgres previously sat in the same red-orange band as accent
    // and error — see index.css comment).
    store: {
      s3: "var(--store-s3)", s3Soft: "var(--store-s3-soft)",
      postgres: "var(--store-postgres)", postgresSoft: "var(--store-postgres-soft)",
      qdrant: "var(--store-qdrant)", qdrantSoft: "var(--store-qdrant-soft)",
    },

    // The Layout view's chunk-grouping outline — one distinct teal for every chunk's dashed container
    // box (never a block/IR type colour, never grey); the forge accent overrides it when active.
    chunkOutline: "var(--chunk-outline)",

    // Vivid IR-TYPE palette for the Layout view — punchy, warm-forward, decoupled from the global
    // status tokens. Content types are saturated; furniture types (text/caption/chrome) stay quiet.
    ir: {
      heading: "var(--ir-heading)",
      list: "var(--ir-list)",
      table: "var(--ir-table)",
      figure: "var(--ir-figure)",
      formula: "var(--ir-formula)",
      caption: "var(--ir-caption)",
      text: "var(--ir-text)",
      chrome: "var(--ir-chrome)",
    },

    // Modal backdrop scrim — same near-black value in both palettes (index.css), so a full-screen
    // dialog's overlay stays visually and semantically identical regardless of theme.
    overlay: "var(--overlay)",
    // A much lighter version of the same near-black, behind the sidebar's TRANSIENT hover/focus
    // overlay only (never behind a pinned/reflowed rail, see Sidebar.tsx) — marks it as a passing
    // flyout rather than a modal-grade interruption.
    overlaySubtle: "var(--overlay-subtle)",
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
