// ====== Code Summary ======
// Canonical design-token module for DocForge.
// This file is the SINGLE source of truth for all design tokens.
// CSS custom properties in global.css are derived from these values.
// NO component file should hardcode any color, font-size, spacing, or other
// visual constant — always reference tokens from here or via CSS vars.
//
// Token philosophy: refined dark (Linear / Vercel-grade).
// Layered surfaces (NOT flat black), real elevation shadows, Inter typography.
// Dark-first (#0e0f13 base, #6366f1 indigo accent), light-variant available.

// ── Palette ──────────────────────────────────────────────────────────────────

/** Raw color palette — dark theme. Never use these directly; use semantic tokens. */
export const palette = {
  // Backgrounds — layered from darkest to lightest; creates visual depth.
  base:            '#0e0f13',
  surface:         '#16181f',
  surfaceRaised:   '#1d2029',  // hover, elevated, inputs
  surfaceOverlay:  '#232734',  // popovers, dropdowns, modals

  // Borders
  border:          '#262a35',  // subtle dividers
  borderStrong:    '#333a49',  // focus rings base, strong dividers

  // Text
  text:            '#e7e9ef',
  textMuted:       '#9aa2b1',
  textDim:         '#6a7180',

  // Accent (indigo — used sparingly)
  accent:          '#6366f1',
  accentHover:     '#7c7ff3',
  accentSoft:      'rgba(99, 102, 241, 0.14)',

  // Elevation shadows — dark theme; these add the depth missing from the old design.
  shadowSm:  '0 1px 2px rgba(0,0,0,.35)',
  shadowMd:  '0 4px 14px rgba(0,0,0,.40)',
  shadowLg:  '0 16px 40px rgba(0,0,0,.50)',
} as const

/** Raw color palette — light theme. */
export const paletteLight = {
  base:            '#f6f7fb',
  surface:         '#ffffff',
  surfaceRaised:   '#f0f2f8',
  surfaceOverlay:  '#ffffff',

  border:          '#e2e6ef',
  borderStrong:    '#cbd0db',

  text:            '#1a1a2a',
  textMuted:       '#5b6478',
  textDim:         '#8d96a8',

  accent:          '#6366f1',
  accentHover:     '#4f46e5',
  accentSoft:      'rgba(99, 102, 241, 0.12)',

  shadowSm:  '0 1px 2px rgba(20,25,40,0.06)',
  shadowMd:  '0 4px 16px rgba(20,25,40,0.10)',
  shadowLg:  '0 16px 40px rgba(20,25,40,0.18)',
} as const

// ── Status / Semantic colors ──────────────────────────────────────────────────

/** Status colors — refined hues with better legibility on layered dark surfaces. */
export const status = {
  done:    '#34d399',  // emerald-400 (mint green — passes on dark surfaces)
  running: '#fbbf24',  // amber-400 (warm amber for in-progress)
  error:   '#f87171',  // red-400 (soft coral — not harsh on dark)
  warning: '#fbbf24',  // same as running (both are caution states)
  info:    '#60a5fa',  // blue-400
  pending: '#94a3b8',
  idle:    '#475569',
  skip:    '#475569',

  // Soft background variants (.14 alpha) — for status badges/tags.
  doneSoft:    'rgba(52, 211, 153, 0.14)',
  warningSoft: 'rgba(251, 191, 36, 0.14)',
  errorSoft:   'rgba(248, 113, 113, 0.14)',
  infoSoft:    'rgba(96, 165, 250, 0.14)',
} as const

// ── Typography ────────────────────────────────────────────────────────────────

export const typography = {
  fonts: {
    /**
     * UI font — Inter first; system-ui as fallback.
     * Inter is loaded via @fontsource/inter (imported in main.tsx).
     * Used for ALL UI text: labels, body, nav, headings.
     */
    ui:   "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
    /**
     * Mono font — ONLY for IDs, hashes, code, keys, API tokens.
     * Never use for labels, body text, or nav items.
     */
    mono: "ui-monospace, 'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace",
  },
  sizes: {
    /** Timestamps, sub-labels, micro badges. */
    xxs:  '9px',
    /** Meta labels, tags, status pills (--text-xs). */
    xs:   '11px',
    /** Dense UI text (--text-sm). */
    sm:   '12.5px',
    /** Body / form text (--text-base, body default). */
    base: '13.5px',
    /** Table rows, form labels (--text-md). */
    md:   '15px',
    /** Section headings (--text-lg). */
    lg:   '18px',
    /** Panel / page titles (--text-xl). */
    xl:   '22px',
  },
  weights: {
    regular:  400,
    medium:   500,
    semibold: 600,
    bold:     700,
  },
  lineHeights: {
    tight: 1.3,
    base:  1.5,
    loose: 1.7,
  },
  /** Default base font size applied to <body>. */
  baseFontSize: '13.5px',
} as const

// ── Spacing ───────────────────────────────────────────────────────────────────

/**
 * 8-px grid spacing scale.
 * --space-1 … --space-8 = 4, 8, 12, 16, 20, 24, 32, 40 px.
 */
export const spacing = {
  0:    '0px',
  0.5:  '2px',
  1:    '4px',   // --space-1
  1.5:  '6px',
  2:    '8px',   // --space-2
  2.5:  '10px',
  3:    '12px',  // --space-3
  4:    '16px',  // --space-4
  5:    '20px',  // --space-5
  6:    '24px',  // --space-6
  7:    '28px',
  8:    '32px',  // --space-7
  10:   '40px',  // --space-8
  12:   '48px',
} as const

// ── Radii ─────────────────────────────────────────────────────────────────────

/**
 * Generous radius scale — rounded feels premium on dark surfaces.
 * sm=tags/badges, md=cards/inputs, lg=drawers/modals.
 */
export const radii = {
  none: '0px',
  sm:   '6px',   // tags, badges, small chips
  base: '10px',  // default — cards, panels, containers
  md:   '10px',  // alias for base (cards/inputs per spec)
  lg:   '14px',  // drawers, modals, overlays
  full: '9999px',
} as const

// ── Elevation ────────────────────────────────────────────────────────────────

/**
 * Shadow scale — the key ingredient for "depth" missing from the old design.
 * Cards: sm/md. Dropdowns/modals: lg.
 */
export const elevation = {
  sm: '0 1px 2px rgba(0,0,0,.35)',
  md: '0 4px 14px rgba(0,0,0,.40)',
  lg: '0 16px 40px rgba(0,0,0,.50)',
  // Legacy numeric aliases kept so old references don't break.
  1: '0 1px 2px rgba(0,0,0,.35)',
  2: '0 4px 14px rgba(0,0,0,.40)',
  3: '0 16px 40px rgba(0,0,0,.50)',
} as const

// ── Z-index layers ────────────────────────────────────────────────────────────

export const zIndex = {
  /** Base content. */
  base:     0,
  /** Sticky headers / toolbars. */
  sticky:   10,
  /** Dropdowns, context menus. */
  dropdown: 100,
  /** Overlays, modals. */
  overlay:  200,
  /** Modal dialogs (above overlay). */
  modal:    201,
  /** Tooltips (highest). */
  tooltip:  300,
} as const

// ── Density metrics ───────────────────────────────────────────────────────────
// Comfortable but still information-dense — breathing room over pure cockpit.

export const density = {
  /** Tall (comfortable) row — form rows, detail panels. */
  rowHeightLg: '40px',
  /** Standard row — document list, search results, table rows. */
  rowHeight:   '36px',
  /** Compact row — dense tables, trace lines. */
  rowHeightSm: '28px',
  /** Micro row — status chips, badges. */
  rowHeightXs: '20px',

  /** Default cell padding (vertical). */
  cellPaddingV:  '6px',
  /** Default cell padding (horizontal). */
  cellPaddingH:  '10px',

  /** Table header height. */
  tableHeaderH: '32px',

  /** Left sidebar width. */
  sidebarWidth:  '220px',
  /** Top bar / context bar height. */
  topbarHeight:  '46px',
  /** Right inspector panel default width. */
  inspectorWidth: '400px',
} as const

// ── Layout ────────────────────────────────────────────────────────────────────

export const layout = {
  topbarH:    density.topbarHeight,
  sidebarW:   density.sidebarWidth,
  inspectorW: density.inspectorWidth,
} as const

// ── CSS var mapping ───────────────────────────────────────────────────────────
// These are the CSS custom property names used in global.css.
// The values are provided by the :root / [data-theme] blocks.
// This map is a reference only — actual injection happens in global.css.

export const vars = {
  bg:              'var(--bg)',
  surface:         'var(--surface)',
  surfaceRaised:   'var(--surface-raised)',
  surfaceOverlay:  'var(--surface-overlay)',
  hover:           'var(--hover)',
  active:          'var(--active)',
  panelBg:         'var(--panel-bg)',

  border:          'var(--border)',
  borderStrong:    'var(--border-strong)',

  text:            'var(--text)',
  textMuted:       'var(--text-muted)',
  textDim:         'var(--text-dim)',

  accent:          'var(--accent)',
  accentSoft:      'var(--accent-soft)',
  accentHover:     'var(--accent-hover)',

  // Legacy names kept for compatibility
  shadow1:         'var(--shadow-sm)',
  shadow2:         'var(--shadow-md)',

  // New elevation vars
  shadowSm:        'var(--shadow-sm)',
  shadowMd:        'var(--shadow-md)',
  shadowLg:        'var(--shadow-lg)',

  fontUi:          'var(--font-ui)',
  fontMono:        'var(--font-mono)',
  fontSize:        'var(--font-size)',

  radius:          'var(--radius)',
  radiusSm:        'var(--radius-sm)',
  radiusMd:        'var(--radius-md)',
  radiusLg:        'var(--radius-lg)',

  topbarH:         'var(--topbar-h)',

  sDone:           'var(--s-done)',
  sRunning:        'var(--s-running)',
  sError:          'var(--s-error)',
  sWarning:        'var(--s-warning)',
  sInfo:           'var(--s-info)',
  sPending:        'var(--s-pending)',
  sIdle:           'var(--s-idle)',

  sDoneSoft:       'var(--s-done-soft)',
  sWarningSoft:    'var(--s-warning-soft)',
  sErrorSoft:      'var(--s-error-soft)',
  sInfoSoft:       'var(--s-info-soft)',
} as const

export default {
  palette,
  paletteLight,
  status,
  typography,
  spacing,
  radii,
  elevation,
  zIndex,
  density,
  layout,
  vars,
}
