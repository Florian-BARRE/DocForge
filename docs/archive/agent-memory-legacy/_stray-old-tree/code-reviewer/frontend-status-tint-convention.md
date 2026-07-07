---
name: frontend-status-tint-convention
description: Frontend uses hardcoded rgba() status tints because the theme has no soft status tokens — do not flag these as hardcoded-color violations
metadata:
  type: feedback
---

In the frontend (`src/docforge/app/frontend/src/global.css`), semi-transparent
status TINT backgrounds are written as hardcoded `rgba(...)` literals — e.g.
`rgba(34,197,94,0.12)` (done), `rgba(239,68,68,0.06)` (error),
`rgba(245,158,11,0.06)` (warning), `rgba(148,163,184,0.10)` (pending).

**Why:** `theme.ts` / `:root` defines only the SOLID status colors
(`--s-done`, `--s-error`, `--s-warning`, `--s-pending`, `--s-running`) plus a
single `--accent-soft`. There is no `--s-done-soft` / `--s-error-soft` family,
so a transparent tint cannot be expressed with an existing token. This pattern
is pervasive and pre-existing across global.css (e.g. lines ~1142, 1148, 2824).
TEXT/border colors in these same rules DO correctly use `var(--s-*)`.

**How to apply:** When reviewing new frontend CSS, do NOT raise a
"hardcoded color / theme-token rule violation" for rgba() tints whose RGB
matches an existing `--s-*` solid color — it is the established convention.
A legitimate suggestion (not a blocker) is "introduce `--s-*-soft` tokens to
the theme so tints become tokenized too." Flag genuinely off-palette hex/rgba
(colors that don't match any token) as real violations.
