// ====== Code Summary ======
// Shared visual + copy definitions for the corpus grid's three search-nature flags (filterable /
// semantic / lexical) — the tiny mono badges under a column header (ColumnNatureBadges) and the
// CorpusFilterPanel legend both render from this single source, so the label/tone/description text
// can never drift between the two surfaces. Deliberately never forge orange (brand.md: orange marks
// the one active thing, never a passive descriptive tag) — each tone reuses an existing semantic
// token rather than inventing a fourth colour family.

import { theme } from "../../../theme";

export type ColumnNatureKey = "filterable" | "semantic" | "lexical";

export interface ColumnNatureBadgeSpec {
  label: string;
  description: string;
  bg: string;
  fg: string;
}

export const COLUMN_NATURE_BADGES: Record<ColumnNatureKey, ColumnNatureBadgeSpec> = {
  // Steel — same hue `theme.color.capability` already reserves for "a passive capability/origin
  // flag" (see theme.ts), which is exactly what "this column has a header filter" is.
  filterable: {
    label: "filter",
    description: "Filterable — exact/range filter",
    bg: theme.color.capabilitySoft,
    fg: theme.color.capabilityStrong,
  },
  // Muted neutral — dense/semantic search is a quieter, less "structured" capability than an exact
  // filter, so it sits a shade further from the steel tone rather than sharing it.
  semantic: {
    label: "dense",
    description: "Semantic search — dense vector on this field",
    bg: theme.color.surface3,
    fg: theme.color.mute,
  },
  // Stale/amber — reuses `theme.color.warn`, documented in index.css as the "ember — stale /
  // attention" ink; BM25 is a sparse/lexical match, a fittingly "rougher" tone than dense.
  lexical: {
    label: "bm25",
    description: "Lexical search — sparse/BM25 on this field",
    bg: theme.color.warnSoft,
    fg: theme.color.warnStrong,
  },
};
