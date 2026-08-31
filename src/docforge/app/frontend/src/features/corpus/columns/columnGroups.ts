// ====== Code Summary ======
// Presentation metadata for the column-visibility menu's grouping — the display order and label
// for each `ColumnGroup`. Document columns lead; the three metadata origins follow in the order a
// reader reasons about provenance (system-derived, then pipeline-generated, then user-declared).

import type { ColumnGroup } from "../types";

export const COLUMN_GROUP_ORDER: ColumnGroup[] = ["document", "system", "generated", "user"];

export const COLUMN_GROUP_LABELS: Record<ColumnGroup, string> = {
  document: "Document",
  system: "System metadata",
  generated: "Generated metadata",
  user: "Upload metadata",
};
