// ====== Code Summary ======
// Humanizes the backend's `score_kind` enum (see SearchResponse.score_kind docstring in
// api/generated.ts) into the short caption shown next to results. An unrecognized/future kind
// still reads honestly — its raw wire value, not a fabricated label.

const SCORE_KIND_LABEL: Record<string, string> = {
  rrf_fusion: "hybrid RRF",
  dbsf_fusion: "hybrid DBSF",
  cross_encoder_rerank: "cross-encoder rerank",
};

/**
 * Turn a raw `score_kind` wire value into its short human caption.
 *
 * Args:
 *   scoreKind: The response's `score_kind`, or undefined on an older/absent-field response.
 *
 * Returns:
 *   The human label, or null when there is nothing to caption.
 */
export function scoreKindLabel(scoreKind: string | undefined): string | null {
  if (!scoreKind) return null;
  return SCORE_KIND_LABEL[scoreKind] ?? scoreKind;
}
