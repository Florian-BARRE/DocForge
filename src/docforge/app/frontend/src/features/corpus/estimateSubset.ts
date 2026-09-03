// ====== Code Summary ======
// Adapts the grid's cross-page `DocumentSelector` (ids XOR filter+excludeIds — see useSelection.ts)
// to the narrower `EstimateSubset` the cost-estimate endpoint accepts (ids XOR filter, no
// `exclude_ids` escape hatch — see api/collections.ts). A "select all matching, minus a few"
// selection collapses to its plain filter for the estimate preview; the excluded few are not
// reflected in the projected cost — acceptable for a preview, never for a bulk mutation.

import type { EstimateSubset } from "../../api/collections";
import type { DocumentFilter, DocumentSelector } from "../../api/corpus";

export function toEstimateSubset(selector: DocumentSelector, filter: DocumentFilter): EstimateSubset {
  if ("document_ids" in selector && selector.document_ids) return { document_ids: selector.document_ids };
  return { filter };
}
