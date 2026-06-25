// ====== Code Summary ======
// Canonical design-token module for DocForge.
// This file is the SINGLE source of truth for all design tokens.
// CSS custom properties in global.css are derived from these values.
// NO component file should hardcode any color, font-size, spacing, or other
// visual constant — always reference tokens from here or via CSS vars.
//
// Token philosophy: dense cockpit (Linear / Datadog / Grafana aesthetics).
// Dark-first (#090910 base, #6366f1 indigo accent), light-variant available.

// ── Palette ──────────────────────────────────────────────────────────────────

/** Raw color palette — dark theme. Never use these directly; use semantic tokens. */
export const palette = {
  // Backgrounds (darkest to lightest)
  base:           '#090910',
  surface:        '#101018',
  surfaceRaised:  '#15151f',
  hover:          '#1b1b28',
  active:         '#222233',

  // Borders
  border:         '#20202e',
  borderStrong:   '#30304a',

  // Text
  text:           '#e8e8f2',
  textMuted:      '#787898',
  textDim:        '#38384e',

  // Accent (indigo)
  accent:         '#6366f1',
  accentSoft:     'rgba(99, 102, 241, 0.16)',
  accentHover:    '#818cf8',

  // Shadows
  shadow1:        '0 1px 2px rgba(0,0,0,0.4)',
  shadow2:        '0 4px 16px rgba(0,0,0,0.5)',
} as const

/** Raw color palette — light theme. */
export const paletteLight = {
  base:           '#f6f7fb',
  surface:        '#ffffff',
  surfaceRaised:  '#ffffff',
  hover:          '#eef0f5',
  active:         '#e2e6ef',

  border:         '#e2e6ef',
  borderStrong:   '#cbd0db',

  text:           '#1a1a2a',
  textMuted:      '#5b6478',
  textDim:        '#8d96a8',

  accent:         '#6366f1',
  accentSoft:     'rgba(99, 102, 241, 0.12)',
  accentHover:    '#4f46e5',

  shadow1:        '0 1px 2px rgba(20, 25, 40, 0.06)',
  shadow2:        '0 4px 16px rgba(20, 25, 40, 0.10)',
} as const

// ── Status / Semantic colors ──────────────────────────────────────────────────

/** Status colors — same hues on both themes for legibility. */
export const status = {
  done:    '#22c55e',
  running: '#d97706',
  error:   '#ef4444',
  warning: '#f59e0b',
  pending: '#94a3b8',
  idle:    '#475569',
  skip:    '#475569',
} as const

// ── Typography ────────────────────────────────────────────────────────────────

export const typography = {
  fonts: {
    /** System UI stack — used for all UI text. */
    ui:   "system-ui, -apple-system, 'Segoe UI', sans-serif",
    /** Monospace stack — used for IDs, traces, code, and dense data. */
    mono: "'JetBrains Mono', 'Cascadia Code', 'Fira Code', ui-monospace, monospace",
  },
  sizes: {
    /** Sub-label, timestamps, micro badges. */
    xxs: '9px',
    /** Meta labels, tags, status pills. */
    xs:  '10px',
    /** Primary dense UI text (default). */
    sm:  '11px',
    /** Base body / form text. */
    base: '12px',
    /** Table rows, form labels. */
    md:  '13px',
    /** Section headings. */
    lg:  '15px',
    /** Panel titles. */
    xl:  '16px',
    /** Modal/page titles. */
    xxl: '20px',
  },
  weights: {
    regular:   400,
    medium:    500,
    semibold:  600,
    bold:      700,
  },
  lineHeights: {
    tight:  1.3,
    base:   1.5,
    loose:  1.7,
  },
  /** Default base font size applied to <body>. */
  baseFontSize: '13px',
} as const

// ── Spacing ───────────────────────────────────────────────────────────────────

/** 4-px base grid spacing scale. */
export const spacing = {
  0:    '0px',
  0.5:  '2px',
  1:    '4px',
  1.5:  '6px',
  2:    '8px',
  2.5:  '10px',
  3:    '12px',
  4:    '16px',
  5:    '20px',
  6:    '24px',
  7:    '28px',
  8:    '32px',
  10:   '40px',
  12:   '48px',
} as const

// ── Radii ─────────────────────────────────────────────────────────────────────

export const radii = {
  none: '0px',
  sm:   '4px',
  base: '6px',
  md:   '8px',
  lg:   '12px',
  full: '9999px',
} as const

// ── Shadows / Elevation ───────────────────────────────────────────────────────

/** Elevation scale — dark theme. */
export const elevation = {
  1: '0 1px 2px rgba(0,0,0,0.4)',
  2: '0 4px 16px rgba(0,0,0,0.5)',
  3: '0 8px 32px rgba(0,0,0,0.6)',
} as const

// ── Z-index layers ────────────────────────────────────────────────────────────

export const zIndex = {
  /** Base content. */
  base:    0,
  /** Dropdowns, context menus. */
  dropdown: 100,
  /** Sticky headers / toolbars. */
  sticky:  10,
  /** Overlays, modals. */
  overlay: 200,
  /** Modal dialogs (above overlay). */
  modal:   201,
  /** Tooltips (highest). */
  tooltip: 300,
} as const

// ── Density metrics ───────────────────────────────────────────────────────────
// Tuned for a cockpit layout: information density over comfort.

export const density = {
  /** Tall (comfortable) row — detail panels, form rows. */
  rowHeightLg: '38px',
  /** Standard row — document list, search results. */
  rowHeight:   '32px',
  /** Compact row — dense tables, trace lines. */
  rowHeightSm: '26px',
  /** Micro row — status chips, badges. */
  rowHeightXs: '20px',

  /** Default cell padding (vertical). */
  cellPaddingV:  '4px',
  /** Default cell padding (horizontal). */
  cellPaddingH:  '8px',

  /** Table header height. */
  tableHeaderH: '28px',

  /** Left sidebar width. */
  sidebarWidth:  '200px',
  /** Top bar / context bar height. */
  topbarHeight:  '44px',
  /** Right inspector panel default width. */
  inspectorWidth: '380px',
} as const

// ── Layout ────────────────────────────────────────────────────────────────────

export const layout = {
  topbarH:       density.topbarHeight,
  sidebarW:      density.sidebarWidth,
  inspectorW:    density.inspectorWidth,
} as const

// ── CSS var mapping ───────────────────────────────────────────────────────────
// These are the CSS custom property names used in global.css.
// The values are provided by the :root / [data-theme] blocks.
// This map is a reference only — the actual injection happens in global.css.

export const vars = {
  bg:             'var(--bg)',
  surface:        'var(--surface)',
  surfaceRaised:  'var(--surface-raised)',
  hover:          'var(--hover)',
  active:         'var(--active)',
  panelBg:        'var(--panel-bg)',

  border:         'var(--border)',
  borderStrong:   'var(--border-strong)',

  text:           'var(--text)',
  textMuted:      'var(--text-muted)',
  textDim:        'var(--text-dim)',

  accent:         'var(--accent)',
  accentSoft:     'var(--accent-soft)',
  accentHover:    'var(--accent-hover)',

  shadow1:        'var(--shadow-1)',
  shadow2:        'var(--shadow-2)',

  fontUi:         'var(--font-ui)',
  fontMono:       'var(--font-mono)',
  fontSize:       'var(--font-size)',

  radius:         'var(--radius)',
  radiusSm:       'var(--radius-sm)',

  topbarH:        'var(--topbar-h)',

  sDone:          'var(--s-done)',
  sRunning:       'var(--s-running)',
  sError:         'var(--s-error)',
  sWarning:       'var(--s-warning)',
  sPending:       'var(--s-pending)',
  sIdle:          'var(--s-idle)',
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
